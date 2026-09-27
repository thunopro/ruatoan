#!/usr/bin/env python3
"""List product nodes (title + link) from biblio.mccme.ru series/tag listings. Metadata only."""
import sys, os, re, html, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch as F
ROOT = F.ROOT
out = {}
for base, maxp in [('https://biblio.mccme.ru/series/170', 10), ('https://biblio.mccme.ru/main?tag=285', 40),
                   ('https://biblio.mccme.ru/main?tag=278', 60), ('https://biblio.mccme.ru/series/174', 10),
                   ('https://biblio.mccme.ru/series/169', 10), ('https://biblio.mccme.ru/series/299', 10)]:
    for p in range(0, maxp):
        u = base + (('&' if '?' in base else '?') + f'page={p}' if p else '')
        m = F.fetch(u)
        if m['status'] != 200: break
        t = open(F.key(u) + '.html', encoding='utf8', errors='replace').read()
        found = 0
        for a, b in re.findall(r'<a href="(/node/\d+)"[^>]*>(.*?)</a>', t, re.S):
            b = ' '.join(html.unescape(re.sub('<[^>]+>', '', b)).split())
            if b and a not in out:
                out[a] = {'node': 'https://biblio.mccme.ru' + a, 'title': b, 'list': base}; found += 1
        if 'page=%d' % (p + 1) not in t: break
json.dump(list(out.values()), open(os.path.join(ROOT, '.cache/books/mccme_biblio.json'), 'w'), ensure_ascii=False, indent=0)
for v in out.values(): print(v['node'], '|', v['title'], '|', v['list'][-10:])
