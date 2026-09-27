#!/usr/bin/env python3
"""Parse math.ru/lib series listings (cached) into rows: num, author, title, year, book page."""
import re, html, sys, json, glob, os
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
rows = []
for fn in sorted(glob.glob(os.path.join(ROOT, '.cache/books/html/mathru_*.html'))):
    t = open(fn, encoding='utf8', errors='replace').read()
    for tr in re.findall(r'<tr class="tbldata\d"[^>]*>(.*?)</tr>', t, re.S):
        tds = re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)
        if len(tds) < 5: continue
        clean = lambda s: ' '.join(html.unescape(re.sub('<[^>]+>', ' ', s)).split())
        link = re.search(r'href="([^"]+)"', tds[2])
        rows.append({'ser': os.path.basename(fn)[7:-5], 'num': clean(tds[0]), 'author': clean(tds[1]), 'title': clean(tds[2]), 'year': clean(tds[3]), 'link': 'https://math.ru' + link.group(1) if link else None})
json.dump(rows, open(os.path.join(ROOT, '.cache/books/mathru_rows.json'), 'w'), ensure_ascii=False, indent=0)
for r in rows: print(r['ser'], r['num'], '|', r['author'], '|', r['title'], '|', r['year'], '|', r['link'])
