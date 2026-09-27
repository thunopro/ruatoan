"""Find «Квант» для младших школьников / Задачи articles in all Kvant issues; fetch article pages (page scans + text if present).
Output: .cache/rusca/kvant/junior.json [{year, issue, url, pages:[jpg urls], text}]"""
import asyncio, json, re, html
from pathlib import Path
import aiohttp
ROOT = Path(__file__).resolve().parents[2]
D = ROOT / '.cache/rusca/kvant'
(D / 'issues').mkdir(parents=True, exist_ok=True)
SEM = asyncio.Semaphore(6)


async def get(sess, url, f):
    if f.exists() and f.stat().st_size > 1000:
        return f.read_text()
    async with SEM:
        for t in range(4):
            try:
                async with sess.get(url) as r:
                    s = await r.text()
                    if r.status == 200:
                        f.write_text(s); return s
                    if r.status == 404:
                        return ''
            except Exception:
                await asyncio.sleep(3)
    return ''


async def main():
    async with aiohttp.ClientSession(headers={'User-Agent': 'Mozilla/5.0'}, timeout=aiohttp.ClientTimeout(total=60)) as sess:
        keys = [(y, n) for y in range(1970, 2027) for n in range(1, 13)]
        pages = await asyncio.gather(*(get(sess, f'https://www.kvant.digital/issues/{y}/{n}/', D / 'issues' / f'{y}_{n}.html') for y, n in keys))
        arts = []
        for (y, n), s in zip(keys, pages):
            if not s:
                continue
            m = re.search(r'Номер\s*</?[^>]*>?\s*(?:<[^>]+>\s*)*([\d/\-–]+)', s)
            # find "для младших школьников" block then first "zadachi-" link after it
            i = s.find('для младших школьников')
            if i < 0:
                continue
            blk = s[i:i + 6000]
            for u in re.findall(r'href="(//www\.kvant\.digital/issues/\d+/[\d\-]+/zadachi-[0-9a-f]+/)"', blk)[:1]:
                arts.append({'year': y, 'n': n, 'url': 'https:' + u})
        print('articles', len(arts))
        outs = await asyncio.gather(*(get(sess, a['url'], D / 'issues' / ('art_' + re.sub(r'\W+', '_', a['url'][30:]) + '.html')) for a in arts))
        for a, s in zip(arts, outs):
            i = s.find('<main')
            a['pages'] = ['https:' + u for u in dict.fromkeys(re.findall(r'<img src="(//www\.kvant\.digital/data/[^"]+/jpg/\d+\.jpg)"', s[i:]))]
            a['has_text'] = 'Текстовое представление статьи находится в процессе подготовки' not in s
            iss = re.search(r'Квант\. — (\d{4})\. — № ([\d/\-–]+)\. — С\. ([\d—\-,\s]+)', html.unescape(s))
            a['issue'] = iss.group(2) if iss else str(a['n'])
        (D / 'junior.json').write_text(json.dumps(arts, ensure_ascii=False, indent=1))
        print('with pages', sum(1 for a in arts if a['pages']), 'text', sum(1 for a in arts if a['has_text']))

asyncio.run(main())
