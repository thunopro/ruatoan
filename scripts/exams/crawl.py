"""Crawl thcs.toanmath.com exam categories -> .cache/exams/catalog.json, download PDFs -> .cache/pdf/.
Usage: python3 scripts/exams/crawl.py [--no-download]"""
import asyncio, html, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import aiohttp
from common import SCRATCH, log, write_json_atomic

API = 'https://thcs.toanmath.com/wp-json/wp/v2/posts'
CATS = {15: 9, 35: 8, 40: 7, 38: 6, 13: 10}
OUT = SCRATCH / 'exams'
PDF_DIR = SCRATCH / 'pdf'
CATALOG = OUT / 'catalog.json'
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) toanthcs-hard crawler', 'Accept-Encoding': 'gzip, deflate'}
PDF_RE = re.compile(r'https?://(?:[a-z]+\.)?toanmath\.com/[\w\-/]*?-pdf/[^"\'\s<>?#]+?\.pdf', re.I)


def classify(title, grade):
    """Return (kind, grade) or None to skip."""
    t = title.lower()
    if re.search(r'mtct|máy tính cầm tay|casio|tiếng anh|bằng tiếng anh', t):
        return None
    if re.match(r'(tuyển tập|tổng hợp|bộ đề)', t):
        return None  # multi-exam compilations (duplicates of individual posts)
    if grade == 10:
        t2 = re.sub(r'không chuyên|cụm chuyên môn', '', t)
        if not re.search(r'chuyên|ptnk|năng khiếu', t2):
            return None
        return ('chuyen', 10)
    kind = 'olympic' if re.search(r'olympic|olympiad', t) else 'hsg'
    return (kind, grade)


async def fetch_cat(sess, cat):
    posts, page = [], 1
    while True:
        url = f'{API}?categories={cat}&per_page=100&page={page}&_fields=id,link,title,date,content'
        for attempt in range(5):
            try:
                async with sess.get(url, headers=UA) as r:
                    if r.status == 400:
                        return posts
                    r.raise_for_status()
                    data = await r.json()
                    total_pages = int(r.headers.get('X-WP-TotalPages', '1'))
                break
            except Exception as e:
                log('retry', url, type(e).__name__)
                await asyncio.sleep(3 * (attempt + 1))
        else:
            raise RuntimeError('failed ' + url)
        posts += data
        log(f'cat {cat} page {page}/{total_pages}: {len(data)}')
        if page >= total_pages or not data:
            return posts
        page += 1


async def download(sess, sem, e, stats):
    dest = PDF_DIR / e['pdf_file']
    if dest.exists() and dest.stat().st_size > 1000:
        stats['have'] += 1
        return
    async with sem:
        for attempt in range(4):
            try:
                async with sess.get(e['pdf'], headers=UA) as r:
                    if r.status == 404:
                        stats['404'] += 1
                        e['pdf_missing'] = True
                        return
                    r.raise_for_status()
                    b = await r.read()
                if not b.startswith(b'%PDF'):
                    raise RuntimeError('not a pdf')
                tmp = dest.with_suffix('.part')
                tmp.write_bytes(b)
                tmp.rename(dest)
                stats['new'] += 1
                return
            except Exception as ex:
                log('dl retry', e['pdf'], type(ex).__name__, str(ex)[:80])
                await asyncio.sleep(4 * (attempt + 1))
        stats['fail'] += 1


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    catalog, seen = [], set()
    stats_posts = {}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as sess:
        for cat, grade in CATS.items():
            posts = await fetch_cat(sess, cat)
            stats_posts[cat] = len(posts)
            for p in posts:
                if p['id'] in seen:
                    continue
                title = html.unescape(re.sub(r'<[^>]+>', '', p['title']['rendered'])).strip()
                c = classify(title, grade)
                if not c:
                    continue
                content = html.unescape(p['content']['rendered'])
                pdfs = list(dict.fromkeys(PDF_RE.findall(content)))
                if not pdfs:
                    log('no pdf:', title)
                    continue
                seen.add(p['id'])
                intro = re.sub(r'<[^>]+>', ' ', content.split('<iframe')[0])
                intro = re.sub(r'\s+', ' ', intro).strip()[:600]
                for i, pdf in enumerate(pdfs):
                    catalog.append(dict(post_id=p['id'], link=p['link'], title=title, date=p['date'], cat=cat,
                                        kind=c[0], grade=c[1], pdf=pdf, intro=intro,
                                        pdf_file=re.sub(r'[^\w.\-]', '_', pdf.rsplit('/', 1)[1]),
                                        part=i))
        log('posts per cat', stats_posts, 'catalog entries', len(catalog))
        write_json_atomic(CATALOG, catalog)
        if '--no-download' not in sys.argv:
            sem = asyncio.Semaphore(8)
            stats = {'have': 0, 'new': 0, '404': 0, 'fail': 0}
            await asyncio.gather(*(download(sess, sem, e, stats) for e in catalog))
            log('download stats', stats)
            write_json_atomic(CATALOG, catalog)
    write_json_atomic(OUT / 'crawl_stats.json', {'posts_per_cat': stats_posts, 'entries': len(catalog)})


if __name__ == '__main__':
    asyncio.run(main())
