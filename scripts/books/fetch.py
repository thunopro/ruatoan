#!/usr/bin/env python3
"""Fetch URLs (GET, follow redirects) with an on-disk cache under .cache/books/pages/.
Usage: echo URL... | python3 fetch.py [--text]  -> prints "status final_url title"
Metadata-only verification: we store the HTML to read title/author, never republish."""
import sys, os, hashlib, json, re, html, concurrent.futures as cf, requests
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, '.cache/books/pages'); os.makedirs(CACHE, exist_ok=True)
UA = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
      'Accept-Language': 'vi,en;q=0.8,ru;q=0.6'}

def key(u): return os.path.join(CACHE, hashlib.md5(u.encode()).hexdigest())

def fetch(u, force=False):
    k = key(u)
    if os.path.exists(k + '.json') and not force:
        return json.load(open(k + '.json'))
    try:
        r = requests.get(u, headers=UA, timeout=45, allow_redirects=True, stream=True)
        ct = r.headers.get('content-type', '')
        body = b''
        if 'html' in ct or 'json' in ct or 'text' in ct:
            body = r.content[:3_000_000]
        else:
            r.close()  # binary (pdf/djvu): status only, do not download
        meta = {'url': u, 'status': r.status_code, 'final': r.url, 'ctype': ct}
        if body:
            open(k + '.html', 'wb').write(body)
            enc = r.encoding or 'utf-8'
            if 'charset' not in ct.lower():
                m = re.search(rb'charset=["\']?([\w-]+)', body[:3000])
                if m: enc = m.group(1).decode()
            t = body.decode(enc, errors='replace')
            m = re.search(r'<title[^>]*>(.*?)</title>', t, re.S | re.I)
            meta['title'] = ' '.join(html.unescape(m.group(1)).split()) if m else ''
            meta['enc'] = enc
    except Exception as e:
        meta = {'url': u, 'status': 0, 'err': str(e)[:200]}
    json.dump(meta, open(k + '.json', 'w'), ensure_ascii=False)
    return meta

def text(u):
    k = key(u)
    if not os.path.exists(k + '.html'): return ''
    m = json.load(open(k + '.json'))
    t = open(k + '.html', 'rb').read().decode(m.get('enc') or 'utf-8', errors='replace')
    t = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', t, flags=re.S | re.I)
    return ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', t)).split())

if __name__ == '__main__':
    urls = [l.strip() for l in sys.stdin if l.strip()]
    force = '--force' in sys.argv
    with cf.ThreadPoolExecutor(8) as ex:
        for m in ex.map(lambda u: fetch(u, force), urls):
            print(m['status'], m['url'], '|', m.get('title', m.get('err', ''))[:100])
