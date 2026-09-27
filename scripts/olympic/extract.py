"""Transcribe official problem statements from downloaded source files (PDF/images/doc) with Gemini.
Input: .cache/olympic/specs.json  [{id, contest, year, title, sourceName, sourceUrl, files:[path], expect, note}]
Output: .cache/olympic/raw/<id>.json  (problems: [{label, src}])
Usage: python3 scripts/olympic/extract.py [id-prefix ...]"""
import asyncio, json, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from common import log, ROOT
from gemini import Gemini, FLASH, LITE, file_part, sha

OLY = ROOT / '.cache/olympic'
RAW = OLY / 'raw'
RAW.mkdir(parents=True, exist_ok=True)

SCHEMA = {'type': 'object', 'properties': {
    'found': {'type': 'boolean'},
    'problems': {'type': 'array', 'items': {'type': 'object', 'properties': {
        'label': {'type': 'string'}, 'statement': {'type': 'string'}}, 'required': ['label', 'statement']}}},
    'required': ['found', 'problems']}

MIME = {'.pdf': 'application/pdf', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif'}


def to_part(p):
    p = Path(p)
    ext = p.suffix.lower()
    if ext in ('.doc', '.docx'):
        pdf = p.with_suffix('.pdf')
        if not pdf.exists():
            subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', '--outdir', str(p.parent), str(p)],
                           capture_output=True, timeout=180)
        p, ext = pdf, '.pdf'
    if ext == '.gif':
        png = p.with_suffix('.png')
        if not png.exists():
            subprocess.run(['convert', str(p), str(png)], capture_output=True)
        p, ext = png, '.png'
    if not p.exists():
        return None
    return file_part(p, MIME[ext])


async def one(g, spec):
    out = RAW / f"{spec['id']}.json"
    if out.exists():
        return
    parts = [x for x in (to_part(f) for f in spec['files']) if x]
    if not parts:
        log('no files', spec['id']); return
    prompt = (f"The attached file(s) contain the official problems of: {spec['contest_full']} {spec['year']}"
              f"{' — ' + spec['note'] if spec.get('note') else ''}.\n"
              "Transcribe EXACTLY the problem statements of this competition/year (not solutions, not other years/contests). "
              "Keep the original wording (English if an English version exists, otherwise the original language). "
              "Write math in LaTeX with $...$ / $$...$$. Describe any figure only if the statement depends on it. "
              f"Label each problem as in the source (e.g. 'Problem 1', 'A1', 'G3', 'C2', 'N4'). {spec.get('expect','')}\n"
              "If the files do not actually contain this competition's problems, return found=false and an empty list. Never invent problems.")
    key = 'oly-extract-' + sha(prompt + ''.join(p['inlineData']['data'][:2000] + str(len(p['inlineData']['data'])) for p in parts))
    try:
        r = await g.generate(parts + [{'text': prompt}], models=LITE[:4] + FLASH, schema=SCHEMA, cache_key=key, temperature=0.1, max_tries=10)
    except Exception as e:
        log('fail', spec['id'], e); return
    res = r['result']
    if not res.get('found') or not res.get('problems'):
        log('not found', spec['id']); return
    probs = [{'label': p['label'].strip(), 'src': p['statement'].strip()} for p in res['problems'] if p['statement'].strip()]
    col = {k: spec[k] for k in ('id', 'contest', 'year', 'title', 'sourceName', 'sourceUrl')}
    col['problems'] = probs
    tmp = out.with_suffix('.tmp')
    tmp.write_text(json.dumps(col, ensure_ascii=False, indent=1)); tmp.rename(out)
    log('ok', spec['id'], len(probs), r['model'])


async def main():
    specs = json.loads((OLY / 'specs.json').read_text())
    pref = sys.argv[1:]
    if pref:
        specs = [s for s in specs if any(s['id'].startswith(p) for p in pref)]
    g = Gemini()
    sem = asyncio.Semaphore(6)
    async def w(s):
        async with sem:
            await one(g, s)
    await asyncio.gather(*(w(s) for s in specs))
    log('stats', g.stats)
    if g.session:
        await g.session.close()

asyncio.run(main())
