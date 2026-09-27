#!/usr/bin/env python3
"""Dump product metadata (name, handle, short description text) from Haravan/Shopify-like
book stores' collection JSON endpoints. Metadata only. Cache under .cache/books/shop/."""
import json, os, sys, time, hashlib, re, html, requests
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, '.cache/books/shop'); os.makedirs(CACHE, exist_ok=True)
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'}

def get(url):
    fn = os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest() + '.json')
    if os.path.exists(fn): return json.load(open(fn))
    for i in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            if r.status_code != 200: return None
            d = r.json(); json.dump(d, open(fn, 'w'), ensure_ascii=False); return d
        except Exception as e:
            print('retry', url, e, file=sys.stderr); time.sleep(2)

def txt(h):
    return ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', h or '')).split())

def crawl(base, coll):
    out = []
    for p in range(1, 60):
        d = get(f'{base}/collections/{coll}/products.json?page={p}&limit=50')
        if not d or not d.get('products'): break
        for pr in d['products']:
            out.append({'store': base, 'coll': coll, 'name': pr.get('name') or pr.get('title'),
                        'handle': pr.get('alias') or pr.get('handle'), 'vendor': pr.get('vendor'),
                        'desc': txt(pr.get('description') or pr.get('body_html'))[:600]})
        if len(d['products']) < 20: break
    return out

if __name__ == '__main__':
    jobs = [a.split('::') for a in sys.argv[1:]]
    allp = []
    for base, coll in jobs:
        r = crawl(base, coll); print(base, coll, len(r), file=sys.stderr); allp += r
    json.dump(allp, open(os.path.join(ROOT, '.cache/books/shop_products.json'), 'w'), ensure_ascii=False, indent=0)
