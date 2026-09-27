"""Claude lane: Claude agents extract + solve exam PDFs while Gemini quota is out.

  python3 scripts/claude_lane/lane.py next <worker>        claim the next unprocessed exam, print its info
  python3 scripts/claude_lane/lane.py save <key> <file>    validate a result JSON and store it
  python3 scripts/claude_lane/lane.py release <key>        give a claim back (e.g. PDF unreadable -> use 'skip')
  python3 scripts/claude_lane/lane.py skip <key> <reason>  mark as not extractable (no problems / only đáp án)
  python3 scripts/claude_lane/lane.py stats

Result file = {"exams": [{"year", "province", "variant", "problems": [{label,text,topics,level,hint,solution,answer}]}]}
USER DECISION: statements only — hint/solution/answer are "" (do not solve).
(same shape as scripts/exams/ingest.py SCHEMA). Stored as .cache/exams/claude/<key>.json = {"model": "claude", "result": ...}.
"""
import json, os, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/lib'))
from common import TOPICS  # noqa

EX = ROOT / '.cache/exams'
DIR = EX / 'claude'
DIR.mkdir(parents=True, exist_ok=True)
GEM = ROOT / '.cache/gemini'


def key_of(e):
    return f'{e["post_id"]}-{e["part"]}'


def years(t):
    return [int(y) for y in re.findall(r'\b(20[0-3]\d|19\d\d)\b', t)]


def prio(e):
    g = 'chuyen' if e['kind'] == 'chuyen' else f'hsg{e["grade"]}'
    tier = 0 if g in ('hsg9', 'chuyen') else {'hsg8': 1, 'hsg7': 2, 'hsg6': 3}.get(g, 3)
    ys = years(e['title'])
    return (tier, -(max(ys) if ys else 0), -e['post_id'])


_GEM_NAMES = None


def gemini_done(e):
    global _GEM_NAMES
    if _GEM_NAMES is None:
        _GEM_NAMES = {f.name.rsplit('_', 1)[0] for v in ('exams-v1', 'exams-v1-lite') if (GEM / v).exists()
                      for f in (GEM / v).iterdir()}
    return e['pdf_file'].removesuffix('.pdf') in _GEM_NAMES


CLAIM_TTL = 45 * 60  # a claim older than this is considered abandoned


def pages(p):
    try:
        out = subprocess.run(['pdfinfo', str(p)], capture_output=True, text=True).stdout
        return int(re.search(r'Pages:\s+(\d+)', out).group(1))
    except Exception:
        return None


def cmd_next(worker):
    cat = json.loads((EX / 'catalog.json').read_text())
    for e in sorted(cat, key=prio):
        k = key_of(e)
        if (DIR / f'{k}.json').exists() or (DIR / f'{k}.skip').exists() or gemini_done(e):
            continue
        pdf = ROOT / '.cache/pdf' / e['pdf_file']
        if not pdf.exists() or pdf.stat().st_size < 1000:
            continue
        claim = DIR / f'{k}.claim'
        if claim.exists() and time.time() - claim.stat().st_mtime > CLAIM_TTL:
            claim.unlink(missing_ok=True)
        try:
            fd = os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        os.write(fd, worker.encode())
        os.close(fd)
        print(json.dumps({'key': k, 'title': e['title'], 'kind': e['kind'], 'grade': e['grade'], 'link': e['link'],
                          'intro': e.get('intro', '')[:400], 'pdf': str(pdf), 'pages': pages(pdf)}, ensure_ascii=False, indent=1))
        return
    print('NO_MORE_WORK')


def katex(strings):
    r = subprocess.run(['node', str(ROOT / 'scripts/lib/katex_check.mjs')], input=json.dumps(strings),
                       capture_output=True, text=True, cwd=ROOT)
    return json.loads(r.stdout)


def cmd_save(k, f):
    try:
        res = json.loads(Path(f).read_text())
    except Exception as ex:
        sys.exit(f'invalid JSON: {ex}')
    errs, strings, where = [], [], []
    exams = res.get('exams')
    if not isinstance(exams, list):
        sys.exit('top level must be {"exams": [...]}')
    for i, x in enumerate(exams):
        for fld in ('year', 'province', 'variant', 'problems'):
            if fld not in x:
                errs.append(f'exams[{i}] missing {fld}')
        for j, p in enumerate(x.get('problems') or []):
            tag = f'exams[{i}].problems[{j}] ({p.get("label")})'
            for fld in ('label', 'text', 'topics', 'level', 'hint', 'solution', 'answer'):
                if fld not in p:
                    errs.append(f'{tag} missing {fld}')
            if not p.get('topics') or any(t not in TOPICS for t in p.get('topics', [])):
                errs.append(f'{tag} bad topics {p.get("topics")} (allowed {TOPICS})')
            if p.get('level') not in (1, 2, 3, 4):
                errs.append(f'{tag} bad level')
            for fld in ('text', 'hint', 'solution', 'answer'):
                if p.get(fld):
                    strings.append(p[fld]); where.append(f'{tag}.{fld}')
    if strings:
        for w, e in zip(where, katex(strings)):
            if e:
                errs.append(f'{w}: KaTeX/markdown error: {e}')
    if errs:
        print('\n'.join(errs[:60]))
        sys.exit(f'{len(errs)} errors — fix and save again')
    tmp = DIR / f'{k}.json.tmp'
    tmp.write_text(json.dumps({'model': 'claude', 'result': res}, ensure_ascii=False))
    tmp.rename(DIR / f'{k}.json')
    (DIR / f'{k}.claim').unlink(missing_ok=True)
    print(f'saved {k}: {sum(len(x["problems"]) for x in exams)} problems')


def main():
    a = sys.argv[1:]
    if a[0] == 'next':
        cmd_next(a[1])
    elif a[0] == 'save':
        cmd_save(a[1], a[2])
    elif a[0] == 'release':
        (DIR / f'{a[1]}.claim').unlink(missing_ok=True)
    elif a[0] == 'skip':
        (DIR / f'{a[1]}.skip').write_text(' '.join(a[2:]))
        (DIR / f'{a[1]}.claim').unlink(missing_ok=True)
    elif a[0] == 'stats':
        n = lambda s: len(list(DIR.glob('*' + s)))
        print({'done': n('.json'), 'claimed': n('.claim'), 'skipped': n('.skip')})


main()
