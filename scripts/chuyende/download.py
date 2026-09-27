"""Download PDFs of selected docs -> .cache/chuyende/pdf/<postid>.pdf (concurrency 3, resumable)."""
import asyncio, json, os, sys
from pathlib import Path
import aiohttp
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from common import SCRATCH, log

DOCS = SCRATCH / 'chuyende' / 'docs.json'
PDF = SCRATCH / 'chuyende' / 'pdf'
HDR = {'Accept-Encoding': 'gzip, deflate', 'Referer': 'https://thcs.toanmath.com/',
       'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36'}


async def one(sess, sem, d):
    out = PDF / f"{d['id']}.pdf"
    if out.exists() and out.stat().st_size > 1000:
        return
    async with sem:
        for attempt in range(4):
            try:
                async with sess.get(d['pdf']) as r:
                    r.raise_for_status()
                    data = await r.read()
                if not data.startswith(b'%PDF'):
                    raise RuntimeError('not a pdf')
                tmp = out.with_suffix('.part')
                tmp.write_bytes(data)
                tmp.rename(out)
                log('ok', d['id'], len(data) // 1024, 'KB', d['title'][:60])
                return
            except Exception as e:
                log('retry', d['id'], type(e).__name__, e)
                await asyncio.sleep(5 * (attempt + 1))
        log('FAILED', d['id'], d['pdf'])


async def main():
    PDF.mkdir(parents=True, exist_ok=True)
    docs = json.loads(DOCS.read_text())
    sem = asyncio.Semaphore(6)
    async with aiohttp.ClientSession(headers=HDR, timeout=aiohttp.ClientTimeout(total=900)) as sess:
        await asyncio.gather(*(one(sess, sem, d) for d in docs))
    log('done')

asyncio.run(main())
