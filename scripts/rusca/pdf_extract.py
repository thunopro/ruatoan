"""Transcribe problem statements (English, LaTeX) from CEMC contest PDFs and Crux Mathematicorum issue PDFs with Gemini.
Writes .cache/rusca/raw/<collection-id>.json (input of translate.py).
Usage: python3 scripts/rusca/pdf_extract.py [cemc|crux] [id-prefix ...]"""
import asyncio, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from common import log, ROOT, write_json_atomic
from gemini import Gemini, FLASH, NoCapacity, file_part, sha

RC = ROOT / '.cache/rusca'
RAW = RC / 'raw'
CA = RC / 'ca'
MODELS = ['gemini-3.5-flash-lite'] + FLASH + ['gemini-3.1-flash-lite', 'gemini-flash-lite-latest', 'gemini-3.1-flash-lite-preview', 'gemini-2.5-flash-lite', 'gemma-4-31b-it', 'gemma-4-26b-a4b-it']

SCHEMA = {'type': 'object', 'properties': {
    'found': {'type': 'boolean'},
    'problems': {'type': 'array', 'items': {'type': 'object', 'properties': {
        'label': {'type': 'string'}, 'statement': {'type': 'string'}, 'proposer': {'type': 'string'}},
        'required': ['label', 'statement', 'proposer']}}},
    'required': ['found', 'problems']}

CEMC = {  # name -> (slug, contest_full, vi title, grade, note)
    'FryerContest': ('fryer', 'Fryer Mathematics Contest (grade 9)', 'Cuộc thi Toán Fryer (Canada, lớp 9)', 9,
                     'Label questions "Bài 1".."Bài 4"; keep all parts (a), (b), (c) of a question inside ONE statement, each part on its own paragraph.'),
    'GaloisContest': ('galois', 'Galois Mathematics Contest (grade 10)', 'Cuộc thi Toán Galois (Canada, lớp 10)', 10,
                      'Label questions "Bài 1".."Bài 4"; keep all parts (a), (b), (c) of a question inside ONE statement, each part on its own paragraph.'),
    'HypatiaContest': ('hypatia', 'Hypatia Mathematics Contest (grade 11)', 'Cuộc thi Toán Hypatia (Canada, lớp 11)', 10,
                       'Label questions "Bài 1".."Bài 4"; keep all parts (a), (b), (c) of a question inside ONE statement, each part on its own paragraph.'),
    'EuclidContest': ('euclid', 'Euclid Mathematics Contest (grade 12)', 'Cuộc thi Toán Euclid (Canada)', 10,
                      'Label questions "Bài 1".."Bài 10"; keep all parts (a), (b), (c) of a question inside ONE statement, each part on its own paragraph.'),
    'CIMC': ('cimc', 'Canadian Intermediate Mathematics Contest', 'Cuộc thi Toán Trung cấp Canada (CIMC)', 9,
             'Label Part A questions "A1".."A6" and Part B questions "B1".."B3"; keep parts (a),(b),(c) of a Part B question inside ONE statement.'),
    'CSMC': ('csmc', 'Canadian Senior Mathematics Contest', 'Cuộc thi Toán Cao cấp Canada (CSMC)', 10,
             'Label Part A questions "A1".."A6" and Part B questions "B1".."B3"; keep parts (a),(b),(c) of a Part B question inside ONE statement.'),
    'CTMCProblems': ('ctmc', 'Canadian Team Mathematics Contest', 'Cuộc thi Toán Đồng đội Canada (CTMC)', 9,
                     'Take the Individual Problems (label "Cá nhân 1", ...) and Team Problems (label "Đồng đội 1", ...). '
                     'SKIP Relay problems and any problem that refers to an answer of another problem. Skip the multiple-choice answer options if any.'),
}
CRUX_NOTE = (
    'This is one issue of the journal Crux Mathematicorum. Transcribe ONLY the NEW problem proposals of this issue, from these sections: '
    'the main "Problems" section (labels are 4-digit numbers like "3381"), "Mayhem Problems" (labels like "M351"), '
    '"Contest Corner" problems (labels like "CC101"), "Olympiad Corner" problems (labels like "OC101"; if they are unnumbered problems '
    'from a named olympiad, label them "<Olympiad name> <number>"), and "Skoliad" contest problems (label "Skoliad <contest> <number>"). '
    'Do NOT transcribe the solutions sections, where old problems are restated before their solutions. Do not transcribe problems of the '
    '"Problem of the Month" or articles. Put the proposer (e.g. "Proposed by John Smith, Univ. of X, USA") only in the proposer field '
    '(name and affiliation, without "Proposed by"); empty if none. French versions: skip, keep English only.')


def cemc_specs():
    out = []
    for f in sorted((CA / 'pdf').glob('*.pdf')):
        m = re.match(r'(\d{4})(.+)\.pdf', f.name)
        y, name = int(m.group(1)), m.group(2)
        if name not in CEMC:
            continue
        sl, full, vi, grade, note = CEMC[name]
        out.append({'id': f'ca-{sl}-{y}', 'out': 'olympic-canada', 'kind': 'olympic', 'lang': 'en', 'year': y, 'grade': grade,
                    'title': f'{vi} {y}', 'sourceName': f'{full} {y} – CEMC, University of Waterloo',
                    'sourceUrl': f'https://cemc.uwaterloo.ca/sites/default/files/documents/{y}/{f.name}',
                    'file': str(f), 'what': f'the official {full} {y}', 'note': note})
    return out


def crux_specs():
    out = []
    for f in sorted((CA / 'crux').glob('CRUXv*n*.pdf')):
        m = re.match(r'CRUXv(\d+)n(\d+)\.pdf', f.name)
        v, n = int(m.group(1)), int(m.group(2))
        y = 1974 + v  # vol 45 = 2019
        out.append({'id': f'crux-{y}-{n:02d}', 'out': 'tapchi-crux', 'kind': 'tapchi', 'lang': 'en', 'year': y, 'grade': 9,
                    'title': f'Tạp chí Crux Mathematicorum (Canada) tập {v} số {n} ({y})',
                    'sourceName': f'Tạp chí Crux Mathematicorum (Canada) tập {v} số {n}/{y}',
                    'sourceUrl': f'https://cms.math.ca/wp-content/uploads/crux-pdfs/{f.name}',
                    'file': str(f), 'what': f'Crux Mathematicorum volume {v} issue {n}', 'note': CRUX_NOTE})
    return out


async def one(g, spec):
    out = RAW / f"{spec['id']}.json"
    if out.exists():
        return
    part = file_part(spec['file'], 'application/pdf')
    prompt = (f"The attached PDF contains {spec['what']}.\n{spec['note']}\n"
              "Transcribe the problem statements EXACTLY (English), not solutions or answers. Write all math in LaTeX with $...$ / $$...$$. "
              "If a statement relies on a diagram, add a precise description of the diagram in words in square brackets. "
              "Omit point values, instructions to students and multiple-choice answer options. Never invent problems. "
              "If the file does not contain such problems, return found=false.")
    key = 'rc-extract/' + sha(prompt + part['inlineData']['data'][:5000] + str(len(part['inlineData']['data'])))
    try:
        r = await g.generate([part, {'text': prompt}], models=MODELS, schema=SCHEMA, cache_key=key, temperature=0.1, max_tries=10)
    except NoCapacity:
        raise
    except Exception as e:
        log('fail', spec['id'], str(e)[:200]); return
    res = r['result']
    if not res.get('found') or not res.get('problems'):
        log('not found', spec['id']); return
    probs, seen = [], set()
    for p in res['problems']:
        lab = re.sub(r'^(Problem|Question)\s*', '', p['label'].strip()).strip().rstrip('.')
        if not p['statement'].strip() or lab in seen:
            continue
        seen.add(lab)
        if re.fullmatch(r'\d{1,2}', lab):
            lab = f'Bài {lab}'
        probs.append({'label': lab, 'src': p['statement'].strip(), 'proposer': '' if spec['out'] == 'olympic-canada' else (p.get('proposer') or '').strip()})
    col = {k: v for k, v in spec.items() if k not in ('file', 'what', 'note')}
    col['problems'] = probs
    write_json_atomic(out, col)
    log('ok', spec['id'], len(probs), r['model'])


async def main():
    which = sys.argv[1]
    specs = cemc_specs() if which == 'cemc' else crux_specs()
    pref = sys.argv[2:]
    if pref:
        specs = [s for s in specs if any(s['id'].startswith(p) for p in pref)]
    g = Gemini(per_slot=2)
    sem = asyncio.Semaphore(8)

    async def w(s):
        async with sem:
            try:
                await one(g, s)
            except NoCapacity as e:
                log('no capacity', s['id'])
    await asyncio.gather(*(w(s) for s in specs))
    log('stats', g.stats)
    if g.session:
        await g.session.close()

asyncio.run(main())
