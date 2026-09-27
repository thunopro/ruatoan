"""Fetch post lists (id, link, title, date, content) for thcs.toanmath.com categories -> .cache/chuyende/posts.json"""
import asyncio, json, sys
from pathlib import Path
import aiohttp
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from common import SCRATCH, log, write_json_atomic

CATS = {54: 6, 11: 7, 52: 8, 3: 9, 14: 10, 58: 9}
API = 'https://thcs.toanmath.com/wp-json/wp/v2/posts'
OUT = SCRATCH / 'chuyende' / 'posts.json'
HDR = {'Accept-Encoding': 'gzip, deflate', 'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36'}


async def fetch_cat(sess, cat):
    posts, page = [], 1
    while True:
        async with sess.get(API, params={'categories': cat, 'per_page': 100, 'page': page,
                                         '_fields': 'id,link,title,date,content'}) as r:
            if r.status == 400:
                break
            r.raise_for_status()
            total = int(r.headers.get('X-WP-TotalPages', '1'))
            data = await r.json()
        for p in data:
            posts.append({'id': p['id'], 'link': p['link'], 'title': p['title']['rendered'], 'date': p['date'],
                          'cat': cat, 'content': p['content']['rendered']})
        log('cat', cat, 'page', page, '/', total, len(data))
        if page >= total:
            break
        page += 1
    return posts


async def main():
    async with aiohttp.ClientSession(headers=HDR, timeout=aiohttp.ClientTimeout(total=300)) as sess:
        res = await asyncio.gather(*(fetch_cat(sess, c) for c in CATS))
    allp = {}
    for ps in res:
        for p in ps:
            if p['id'] in allp:
                allp[p['id']].setdefault('cats', [allp[p['id']]['cat']]).append(p['cat'])
            else:
                allp[p['id']] = p
    write_json_atomic(OUT, list(allp.values()))
    log('posts', len(allp))

asyncio.run(main())
