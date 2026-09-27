#!/usr/bin/env python3
"""Look up books on the Google Books API (metadata only). stdin: 'query||expected-author-substring'."""
import sys, os, json, hashlib, requests, urllib.parse as up, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch as F
CACHE = os.path.join(F.ROOT, '.cache/books/gbooks'); os.makedirs(CACHE, exist_ok=True)

def search(q):
    u = 'https://www.googleapis.com/books/v1/volumes?maxResults=10&q=' + up.quote(q)
    fn = os.path.join(CACHE, hashlib.md5(u.encode()).hexdigest() + '.json')
    if os.path.exists(fn): return json.load(open(fn))
    for i in range(4):
        r = requests.get(u, timeout=30)
        if r.status_code == 200:
            d = r.json(); json.dump(d, open(fn, 'w')); return d
        time.sleep(3 * (i + 1))
    return {}

if __name__ == '__main__':
    for line in sys.stdin:
        line = line.strip()
        if not line or line.startswith('#'): continue
        q, _, au = line.partition('||')
        d = search(q)
        best = None
        for it in d.get('items', []):
            vi = it['volumeInfo']
            auth = ', '.join(vi.get('authors', []))
            if au and au.lower() not in auth.lower(): continue
            best = (it['id'], vi.get('title', ''), vi.get('subtitle', ''), auth, vi.get('publisher', ''), vi.get('publishedDate', ''))
            break
        print(q, '=>', best)
