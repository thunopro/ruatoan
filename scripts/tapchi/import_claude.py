"""Import manual (Claude) transcriptions .cache/tapchi/claude/out/<mag>-<key>.json into state files, then assemble.
  python3 scripts/tapchi/import_claude.py --mag thtt"""
import argparse, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run  # noqa
import solve as S  # noqa
from common import log, write_json_atomic  # noqa

ap = argparse.ArgumentParser()
ap.add_argument('--mag', default='thtt')
a = ap.parse_args()
idx = {i['key']: i for i in run.load_index(a.mag)}
n = 0
for f in sorted((run.TC / 'claude' / 'out').glob(f'{a.mag}-*.json')):
    key = f.stem[len(a.mag) + 1:]
    it = idx.get(key)
    if not it:
        log('unknown issue', f.name)
        continue
    try:
        o = json.loads(f.read_text())
    except Exception as e:
        log('bad json', f.name, e)
        continue
    st = run.load_state(it)
    if st.get('problems') and st.get('extract_model') != 'claude':
        st['gemini_problems'] = st['problems']   # keep the Gemini transcription for reference; Claude's wins
    st.update({k: it[k] for k in ('mag', 'key', 'num', 'label', 'url', 'year_hint')})
    probs, seen = [], set()
    for p in o.get('problems') or []:
        code = run.norm_code(a.mag, p.get('code'), it['label'])
        if not code or code in seen or not (p.get('text') or '').strip():
            continue
        seen.add(code)
        topics = [t for t in dict.fromkeys(p.get('topics') or []) if t in S.TOPICS][:2] or ['dai-so']
        probs.append({'code': code, 'section': p.get('section') or 'THCS', 'grade_note': (p.get('grade_note') or '').strip(),
                      'text': p['text'].strip(), 'proposer': re.sub(r'\(?\s*[\w.+-]+@[\w.-]+\s*\)?', '', p.get('proposer') or '').strip(), 'complete': True, 'topics': topics})
    st['loc'] = {'pages': o.get('pages') or [], 'issue': str(o.get('issue') or key), 'month': o.get('month') or 0, 'year': o.get('year') or 0}
    st['meta'] = {'issue': str(o.get('issue') or key), 'month': o.get('month') or 0, 'year': o.get('year') or 0}
    st['extract_model'] = 'claude'
    st['problems'] = probs
    st['status'] = 'extracted'
    run.save_state(it, st)
    n += 1
log('imported', n)
run.assemble(a.mag)
