"""Prepare issues that Gemini couldn't transcribe (quota / RECITATION) for manual (Claude) transcription:
download -> thumbnails -> locate section (gemma, else contact sheets) -> hi-res pages -> manifest.
  python3 scripts/tapchi/prep_claude.py --mag thtt
Manifest: .cache/tapchi/claude/<mag>-manifest.json  [{key, label, url, pages:[jpg], sheets:[jpg], loc}]"""
import argparse, asyncio, glob, json, os, sys, faulthandler, signal
faulthandler.register(signal.SIGUSR1)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run  # noqa
from gemini import GEMMA, file_part  # noqa
from common import CACHE, log, write_json_atomic  # noqa

OUT = run.TC / 'claude'
OUT.mkdir(exist_ok=True)


def _sheets(d, th, per=12, cols=6, w=420, h=594):
    from PIL import Image, ImageDraw
    out = []
    for si in range(0, len(th), per):
        grp = th[si:si + per]
        rows = (len(grp) + cols - 1) // cols
        sheet = Image.new('L', (cols * w, rows * (h + 30)), 255)
        dr = ImageDraw.Draw(sheet)
        for i, f in enumerate(grp):
            im = Image.open(f).convert('L')
            im.thumbnail((w - 8, h))
            x, y = (i % cols) * w, (i // cols) * (h + 30)
            sheet.paste(im, (x + 4, y + 28))
            dr.text((x + 8, y + 4), f'Trang {si + i + 1}', fill=0)
        f = d / f'sheet-{si // per:02d}.jpg'
        sheet.save(f, quality=70)
        out.append(str(f))
    return out


async def sheets(it, th, sem):
    d = run.IMG / run.fid(it)
    fs = sorted(glob.glob(str(d / 'sheet-*.jpg')))
    if fs:
        return fs
    async with sem:
        return await asyncio.to_thread(_sheets, d, th)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mag', default='thtt')
    ap.add_argument('--nogemma', action='store_true')
    a = ap.parse_args()
    g = run.G(int(os.environ.get('GEM', '2')))
    idx = run.load_index(a.mag)
    todo = []
    for it in idx:
        st = run.load_state(it)
        if not st.get('problems'):
            todo.append(it)
    log('todo', len(todo))
    located = {}
    for f in run.STATE.glob(f'{a.mag}-*.json'):
        o = json.loads(f.read_text())
        if o.get('problems') and (o.get('loc') or {}).get('pages'):
            located[o['num']] = o['loc']['pages']
    sems = {'dl': asyncio.Semaphore(8), 'cpu': asyncio.Semaphore(3)}
    man, isem = [], asyncio.Semaphore(10)

    async def one(it):
        async with isem:
            pdf = await run.download(it, sems['dl'])
            if not pdf:
                log('no pdf', it['key'])
                return
            th = await run.thumbs(it, pdf, sems['cpu'])
            loc = None
            cp = CACHE / f'tapchi/{a.mag}-loc-v1/{it["key"]}.json'
            if cp.exists():
                loc = json.loads(cp.read_text())['result']
            elif not a.nogemma:
                parts = []
                for i, f in enumerate(th):
                    parts += [{'text': f'Trang {i + 1}:'}, file_part(f, 'image/jpeg')]
                parts.append({'text': run.MAGS[a.mag]['loc_prompt']})
                try:
                    r = await g.gen(parts, models=GEMMA, schema=run.LOC_SCHEMA, max_tries=4,
                                    cache_key=f'tapchi/{a.mag}-loc-gemma/{it["key"]}')
                    loc = r['result']
                except Exception as e:
                    log('gemma loc fail', it['key'], str(e)[:80])
            pages = sorted({p for p in (loc or {}).get('pages') or [] if 1 <= p <= len(th)})[:3]
            rec = {'key': it['key'], 'label': it['label'], 'num': it['num'], 'url': it['url'], 'loc': loc,
                   'npages': len(th), 'pdf': str(pdf), 'img_dir': str(run.IMG / run.fid(it))}
            if pages:
                rec['located'] = pages
            else:   # guess from the nearest issue whose section was located
                near = sorted(located.items(), key=lambda kv: abs(kv[0] - it['num']))
                if near and abs(near[0][0] - it['num']) <= 15:
                    rec['guess'] = [q for q in near[0][1] if 1 <= q <= len(th)]
            rec['sheets'] = await sheets(it, th, sems['cpu'])
            man.append(rec)
            log('prepped', it['key'], pages)

    async def safe(it):
        try:
            await one(it)
        except Exception as e:
            import traceback
            log('ERR', it['key'], traceback.format_exc()[-600:])

    await asyncio.gather(*(safe(it) for it in todo))
    man.sort(key=lambda r: -r['num'])
    write_json_atomic(OUT / f'{a.mag}-manifest.json', man)
    log('manifest', len(man), 'located', sum(1 for r in man if r.get('located')))
    if g.g.session:
        await g.g.session.close()

asyncio.run(main())
