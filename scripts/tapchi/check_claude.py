"""Validate manual transcription files: python3 scripts/tapchi/check_claude.py .cache/tapchi/claude/out/thtt-560.json [...]"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import solve as S  # noqa

TOP = {'so-hoc', 'dai-so', 'bat-dang-thuc', 'hinh-hoc', 'to-hop', 'nghiem-nguyen', 'phuong-trinh'}
bad = 0
for fn in sys.argv[1:]:
    try:
        o = json.loads(Path(fn).read_text())
    except Exception as e:
        print(fn, 'INVALID JSON', e); bad += 1; continue
    ps = o.get('problems') or []
    texts = [p.get('text', '') for p in ps]
    errs = S.katex_check(texts)
    for p, e in zip(ps, errs):
        msg = []
        if e: msg.append('katex: ' + e)
        if not re.match(r'^T?\d+/\d+$', (p.get('code') or '').replace(' ', '')): msg.append('bad code')
        if p.get('section') not in ('THCS', 'THPT'): msg.append('bad section')
        if not p.get('topics') or set(p['topics']) - TOP: msg.append('bad topics')
        for k in ('hint', 'solution', 'answer', 'level'):
            if k in p: msg.append('forbidden field ' + k)
        if msg:
            bad += 1; print(fn, p.get('code'), '; '.join(msg))
    print(fn, len(ps), 'problems', 'issue', o.get('issue'), o.get('month'), o.get('year'))
print('BAD' if bad else 'OK', bad)
