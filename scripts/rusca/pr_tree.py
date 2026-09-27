"""Crawl problems.ru source trees (MCCME) -> .cache/rusca/pr/tree.json and leaf problem lists.
Usage: python3 scripts/rusca/pr_tree.py"""
import asyncio, json, re, html, sys
from pathlib import Path
import aiohttp
ROOT = Path(__file__).resolve().parents[2]
D = ROOT / '.cache/rusca/pr'
(D / 'html').mkdir(parents=True, exist_ok=True)
BASE = 'https://problems.ru/view_by_source_new.php?parent='
ROOTS = {'mmo': 164898, 'tot': 187098, 'vmo': 204607, 'prazdnik': 198948, 'ustn67': 212358, 'euler': 212754, 'okrug': 199837}
SEM = asyncio.Semaphore(4)


async def fetch(sess, pid):
    f = D / 'html' / (str(pid).replace('&start=', '_') + '.html')
    if f.exists() and f.stat().st_size > 3000:
        return f.read_text()
    async with SEM:
        for t in range(5):
            try:
                async with sess.post(BASE + str(pid) + ('' if '&' in str(pid) else '&start=0'), data={'viewing_params[view_amount]': '100', 'viewing_params[submit]': '1'}) as r:
                    b = await r.read()
                s = b.decode('utf8', 'replace')
                if 'componentbox' in s:
                    f.write_text(s)
                    return s
            except Exception as e:
                print('err', pid, e)
            await asyncio.sleep(3 * (t + 1))
    return ''


def parse(s, pid):
    t = re.sub(r'<script.*?</script>', '', s, flags=re.S)
    # children: links after the current node in header box
    i = t.find('id="header_box_contents"')
    hdr = t[i:t.find('</div>', i)]
    links = re.findall(r'href="/view_by_source_new\.php\?parent=(\d+)"[^>]*>(.*?)</a>', hdr, re.S)
    children = [(int(a), html.unescape(re.sub(r'<[^>]+>', '', b)).strip()) for a, b in links]
    total = re.search(r'Всего задач: (\d+)', t)
    probs = []
    for m in re.finditer(r'<a name="problem_(\d+)"></a>(.*?)<table class="problemfootertable">', t, re.S):
        body = m.group(2)
        num = re.search(r'\(#([^)]+)\)', body)
        cls = re.search(r'Классы: ([\d,]+)', body)
        diff = re.search(r'Сложность: ([\d+\-]+)', body)
        stmt = body[body.find('</table>\n<p/>') + 13:] if '</table>\n<p/>' in body else body.split('</table>')[-1]
        probs.append({'pid': int(m.group(1)), 'num': num.group(1).strip() if num else None,
                      'classes': cls.group(1) if cls else '', 'diff': diff.group(1) if diff else '', 'html': stmt.strip()})
    return children, int(total.group(1)) if total else 0, probs


async def walk(sess, pid, name, path, out):
    s = await fetch(sess, pid)
    children, total, probs = parse(s, pid)
    node = {'pid': pid, 'name': name, 'path': path, 'total': total}
    if children and not path and False:
        pass
    if children:
        node['children'] = await asyncio.gather(*(walk(sess, c, n, path + [n], out) for c, n in children))
    else:
        start = 100
        while total > start:
            s2 = await fetch(sess, f'{pid}&start={start}')
            probs += parse(s2, pid)[2]
            start += 100
        node['problems'] = probs
        out.append(node)
    return node


async def main():
    jar = aiohttp.CookieJar()
    async with aiohttp.ClientSession(cookie_jar=jar, headers={'User-Agent': 'Mozilla/5.0'}, timeout=aiohttp.ClientTimeout(total=120)) as sess:
        async with sess.post(BASE + '164898', data={'difficulty_min': '1', 'difficulty_max': '10', 'grade_min': '5', 'grade_max': '11'}) as r:
            await r.read()
        for key, pid in ROOTS.items():
            if len(sys.argv) > 1 and key not in sys.argv[1:]:
                continue
            leaves = []
            await walk(sess, pid, key, [], leaves)
            (D / f'leaves-{key}.json').write_text(json.dumps(leaves, ensure_ascii=False, indent=1))
            print(key, len(leaves), sum(len(l['problems']) for l in leaves), flush=True)

asyncio.run(main())
