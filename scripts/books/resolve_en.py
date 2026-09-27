#!/usr/bin/env python3
"""Resolve English/Russian book titles to a fetchable catalog page.
Open Library search (for ISBNs) -> goodreads.com/book/isbn/<isbn> (follows redirect to the book page).
stdin: 'title||author'. Output: title, goodreads final URL, page title. Metadata only."""
import sys, os, json, hashlib, requests, urllib.parse as up, time, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch as F
CACHE = os.path.join(F.ROOT, '.cache/books/olib'); os.makedirs(CACHE, exist_ok=True)
UA = {'User-Agent': 'ruatoan-catalog/1.0 (metadata lookup)'}

def search(title, author):
    u = 'https://openlibrary.org/search.json?limit=5&fields=key,title,author_name,first_publish_year,isbn,edition_count&title=' + up.quote(title) + ('&author=' + up.quote(author) if author else '')
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

def norm(s): return re.sub(r'[^a-z0-9а-я]+', ' ', s.lower())

def resolve(title, author, isbns=None):
    d = search(title, author)
    docs = sorted(d.get('docs', []), key=lambda x: -(x.get('edition_count') or 0))
    cand = list(isbns or [])
    for doc in docs[:2]:
        cand += [i for i in doc.get('isbn', []) if len(i) == 13][:6] + [i for i in doc.get('isbn', []) if len(i) == 10][:3]
    key_words = [w for w in norm(title).split() if len(w) > 3][:3]
    for isbn in cand[:10]:
        m = F.fetch('https://www.goodreads.com/book/isbn/' + isbn)
        t = m.get('title', '')
        if m['status'] == 200 and '/book/show/' in m.get('final', '') and all(w in norm(t) for w in key_words[:2]):
            return m['final'].split('?')[0], t, (docs[0].get('author_name') if docs else None), (docs[0].get('first_publish_year') if docs else None)
    return None, None, (docs[0].get('author_name') if docs else None), None

if __name__ == '__main__':
    for line in sys.stdin:
        line = line.strip()
        if not line or line.startswith('#'): continue
        parts = line.split('||')
        t, a = parts[0], (parts[1] if len(parts) > 1 else '')
        isb = parts[2].split(',') if len(parts) > 2 and parts[2] else None
        url, pt, au, yr = resolve(t, a, isb)
        print(f'{t} || {url} || {pt} || {au} || {yr}', flush=True)
