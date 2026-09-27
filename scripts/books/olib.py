#!/usr/bin/env python3
"""Look up books on openlibrary.org search API (metadata only).
stdin lines: 'title||author-substring'. Prints best work key, title, authors, year."""
import sys, os, json, hashlib, requests, urllib.parse as up, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch as F
CACHE = os.path.join(F.ROOT, '.cache/books/olib'); os.makedirs(CACHE, exist_ok=True)
UA = {'User-Agent': 'toanthcs-hard-catalog/1.0 (metadata lookup)'}

def search(title, author):
    u = 'https://openlibrary.org/search.json?limit=10&fields=key,title,subtitle,author_name,first_publish_year,publisher,edition_count&title=' + up.quote(title) + ('&author=' + up.quote(author) if author else '')
    fn = os.path.join(CACHE, hashlib.md5(u.encode()).hexdigest() + '.json')
    if os.path.exists(fn): return json.load(open(fn))
    for i in range(4):
        try:
            r = requests.get(u, headers=UA, timeout=60)
            if r.status_code == 200:
                d = r.json(); json.dump(d, open(fn, 'w')); return d
        except Exception: pass
        time.sleep(3 * (i + 1))
    return {}

if __name__ == '__main__':
    for line in sys.stdin:
        line = line.strip()
        if not line or line.startswith('#'): continue
        t, _, a = line.partition('||')
        d = search(t, a)
        docs = d.get('docs', [])
        docs.sort(key=lambda x: -(x.get('edition_count') or 0))
        b = docs[0] if docs else None
        if b:
            print(f"{t} => https://openlibrary.org{b['key']} | {b.get('title')} | {', '.join(b.get('author_name', [])[:4])} | {b.get('first_publish_year')} | ed={b.get('edition_count')}")
        else:
            print(f"{t} => NONE")
