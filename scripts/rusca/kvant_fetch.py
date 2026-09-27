"""Fetch Kvant "Задачник Кванта" math problems M1..Mn from kvant.digital (statement + proposer + issue).
Output: .cache/rusca/kvant/problems.json  [{num, year, issue, html, proposer, figs:[url]}]"""
import asyncio, json, re, html, sys
from pathlib import Path
import aiohttp
ROOT = Path(__file__).resolve().parents[2]
D = ROOT / '.cache/rusca/kvant'
(D / 'html').mkdir(parents=True, exist_ok=True)
SEM = asyncio.Semaphore(6)
MAXN = int(sys.argv[1]) if len(sys.argv) > 1 else 2910


async def fetch(sess, n):
    f = D / 'html' / f'm{n}.html'
    if f.exists():
        return f.read_text()
    async with SEM:
        for t in range(4):
            try:
                async with sess.get(f'https://www.kvant.digital/problems/m{n}/') as r:
                    if r.status == 404:
                        f.write_text(''); return ''
                    s = await r.text()
                if r.status == 200:
                    f.write_text(s); return s
            except Exception as e:
                print('err', n, e)
            await asyncio.sleep(3 * (t + 1))
    return ''


def parse(n, s):
    i = s.find('Условие задачи')
    if i < 0:
        return None
    mm = re.search(r'Квант\. — (\d{4})\. — № ([\d/\-–]+)\. — Стр\. (\d+)', s)
    year, issue, page = (int(mm.group(1)), mm.group(2), int(mm.group(3))) if mm else (None, None, None)
    view = re.search(r'href="//www\.kvant\.digital/view/([^/]+)/p(\d+)/"', s[i:])
    base = {'num': n, 'year': year, 'issue': issue, 'page': page,
            'view': (view.group(1), int(view.group(2))) if view else None}
    j = s.find('<div class="blurer--content mark--hlwords--text">', i)
    end = s.find('<div class="media--screen no-copy block--buttons', i)
    if j < 0 or (end > 0 and j > end):
        base.update(html=None, proposer='', figs=[])
        return base
    k = s.find('<div class="blurer--content meta--extra', j)
    stmt = s[j + len('<div class="blurer--content mark--hlwords--text">'):(k if 0 < k < end else end)]
    prop = ''
    if 0 < k < end:
        pm = re.search(r'<p class="meta--inscription">(.*?)</p>', s[k:end], re.S)
        if pm:
            prop = html.unescape(re.sub(r'<[^>]+>', '', pm.group(1))).replace('\xa0', ' ').strip()
    if 'Текст задачи готовится' in stmt:
        base.update(html=None, proposer='', figs=[])
        return base
    figs = ['https:' + u if u.startswith('//') else u for u in re.findall(r'<img src="([^"]+)"', stmt)]
    base.update(html=stmt.strip(), proposer=prop, figs=figs)
    return base


async def main():
    async with aiohttp.ClientSession(headers={'User-Agent': 'Mozilla/5.0'}, timeout=aiohttp.ClientTimeout(total=60)) as sess:
        pages = await asyncio.gather(*(fetch(sess, n) for n in range(1, MAXN + 1)))
    out = [p for p in (parse(n, s) for n, s in zip(range(1, MAXN + 1), pages) if s) if p]
    (D / 'problems.json').write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print('kvant', len(out), 'figs', sum(1 for p in out if p['figs']))

asyncio.run(main())
