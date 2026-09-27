#!/usr/bin/env python3
"""Crawl post titles (metadata only) from toanmath WP REST API for book discovery.
Caches raw JSON pages under .cache/books/wp/."""
import json, os, sys, time, hashlib, requests
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, '.cache/books/wp')
os.makedirs(CACHE, exist_ok=True)
UA = {'User-Agent': 'Mozilla/5.0 (toanthcs-hard catalog bot)'}

def get(url):
    fn = os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest() + '.json')
    if os.path.exists(fn):
        return json.load(open(fn))
    for i in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            if r.status_code == 400:
                return []
            r.raise_for_status()
            d = r.json(); json.dump(d, open(fn, 'w'), ensure_ascii=False); return d
        except Exception as e:
            print('retry', url, e, file=sys.stderr); time.sleep(3)
    return []

def crawl(site, params):
    out = []
    for p in range(1, 50):
        d = get(f'https://{site}/wp-json/wp/v2/posts?per_page=100&page={p}&_fields=id,link,title,date,categories&{params}')
        if not d: break
        out += d
        if len(d) < 100: break
    return out

if __name__ == '__main__':
    res = {}
    for cat in [54, 11, 52, 3, 14]:
        res[f'thcs-{cat}'] = crawl('thcs.toanmath.com', f'categories={cat}')
    for q in ['sách', 'tuyển tập', 'chuyên đề', 'bồi dưỡng', 'nâng cao', 'THCS', 'lớp 9', 'lớp 8', 'lớp 7', 'lớp 6', 'số học', 'bất đẳng thức', 'hình học', 'tổ hợp']:
        res[f'tm-{q}'] = crawl('toanmath.com', 'search=' + requests.utils.quote(q))
        res[f'thcs-{q}'] = crawl('thcs.toanmath.com', 'search=' + requests.utils.quote(q))
    seen = {}
    for k, v in res.items():
        for p in v:
            seen[p['link']] = {'title': p['title']['rendered'], 'link': p['link'], 'date': p['date'], 'cats': p.get('categories')}
    json.dump(list(seen.values()), open(os.path.join(ROOT, '.cache/books/toanmath_posts.json'), 'w'), ensure_ascii=False, indent=0)
    print(len(seen))
