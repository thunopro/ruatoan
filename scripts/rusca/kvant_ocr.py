"""Transcribe Kvant M-problems whose text is not yet available on kvant.digital, from the issue page scans (Gemini vision).
Input: .cache/rusca/kvant/problems.json (html=None entries, with view=[issue_id, pN]).
Output: .cache/rusca/kvant/ocr.json {num: {src, proposer}}"""
import asyncio, json, re, sys
from pathlib import Path
import aiohttp
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from common import log, ROOT, write_json_atomic
from gemini import Gemini, FLASH, NoCapacity, file_part, sha

RC = ROOT / '.cache/rusca'
K = RC / 'kvant'
PG = K / 'pages'
PG.mkdir(parents=True, exist_ok=True)
MODELS = ['gemini-3.5-flash-lite'] + FLASH + ['gemini-3.1-flash-lite', 'gemini-flash-lite-latest', 'gemini-3.1-flash-lite-preview', 'gemini-2.5-flash-lite', 'gemma-4-31b-it', 'gemma-4-26b-a4b-it']
SCHEMA = {'type': 'object', 'properties': {'problems': {'type': 'array', 'items': {'type': 'object', 'properties': {
    'number': {'type': 'integer'}, 'statement': {'type': 'string'}, 'proposer': {'type': 'string'}},
    'required': ['number', 'statement', 'proposer']}}}, 'required': ['problems']}


async def page(sess, issue, n):
    f = PG / f'{issue}_{n:04d}.jpg'
    if f.exists() and f.stat().st_size > 1000:
        return f
    for t in range(3):
        try:
            async with sess.get(f'https://www.kvant.digital/data/{issue}/jpg/{n:04d}.jpg') as r:
                b = await r.read()
                if r.status == 200 and len(b) > 1000:
                    f.write_bytes(b)
                    return f
                if r.status == 404:
                    return None
        except Exception:
            await asyncio.sleep(3)
    return None


async def main():
    probs = json.loads((K / 'problems.json').read_text())
    outp = K / 'ocr.json'
    done = json.loads(outp.read_text()) if outp.exists() else {}
    groups = {}
    for p in probs:
        if p['html'] is None and p.get('view') and str(p['num']) not in done:
            groups.setdefault(tuple(p['view']), []).append(p['num'])
    log('groups', len(groups), 'problems', sum(len(v) for v in groups.values()))
    g = Gemini(per_slot=2)
    sem = asyncio.Semaphore(8)
    lock = asyncio.Lock()
    stop = [False]
    async with aiohttp.ClientSession(headers={'User-Agent': 'Mozilla/5.0'}, timeout=aiohttp.ClientTimeout(total=90)) as sess:
        async def one(key, nums):
            if stop[0]:
                return
            issue, pn = key
            async with sem:
                files = [f for f in [await page(sess, issue, pn - 1), await page(sess, issue, pn)] if f]
                if not files:
                    log('no pages', key); return
                labels = ', '.join(f'М{n}' for n in nums)
                prompt = ('The attached images are scanned pages of the Russian magazine «Квант», section «Задачник „Кванта“». '
                          f'Transcribe EXACTLY (in Russian) the statements of the MATHEMATICS problems {labels} only '
                          '(not physics problems Ф..., not solutions). Write all math in LaTeX $...$ / $$...$$. Sub-items as "а) ...", "б) ..." '
                          'on separate paragraphs. If a problem has a figure, add a precise description of the figure in Russian in square brackets. '
                          'proposer = the author name printed after the statement (e.g. "А. Толпыго"), empty if none. '
                          'number = the integer after М. Skip problems not visible on these pages. Never invent text.')
                parts = [file_part(f, 'image/jpeg') for f in files] + [{'text': prompt}]
                try:
                    r = await g.generate(parts, models=MODELS, schema=SCHEMA, cache_key=f'rc-kvocr/{issue}-{pn}-{sha(labels)}',
                                         temperature=0.1, max_tries=10)
                except NoCapacity:
                    stop[0] = True; return
                except Exception as e:
                    log('fail', key, str(e)[:150]); return
                got = 0
                async with lock:
                    for it in r['result'].get('problems', []):
                        if it.get('number') in nums and len((it.get('statement') or '')) > 20:
                            done[str(it['number'])] = {'src': it['statement'].strip(), 'proposer': (it.get('proposer') or '').strip(), 'model': r['model']}
                            got += 1
                    write_json_atomic(outp, done)
                log('ok', key, f'{got}/{len(nums)}', r['model'])
        await asyncio.gather(*(one(k, v) for k, v in groups.items()))
    log('stats', g.stats, 'total', len(done))
    if g.session:
        await g.session.close()

asyncio.run(main())
