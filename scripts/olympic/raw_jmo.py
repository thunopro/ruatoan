"""USAJMO statements from Evan Chen's public solution-notes .tex (statements only are used).
Writes .cache/olympic/raw/oly-usajmo-<year>.json"""
import json, re, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / '.cache/olympic/jmo'
RAW = ROOT / '.cache/olympic/raw'
RAW.mkdir(parents=True, exist_ok=True)
MACROS = [(r'\\ZZ(?![a-zA-Z])', r'\\mathbb{Z}'), (r'\\RR(?![a-zA-Z])', r'\\mathbb{R}'), (r'\\QQ(?![a-zA-Z])', r'\\mathbb{Q}'),
          (r'\\NN(?![a-zA-Z])', r'\\mathbb{N}'), (r'\\CC(?![a-zA-Z])', r'\\mathbb{C}'), (r'\\FF(?![a-zA-Z])', r'\\mathbb{F}'),
          (r'\\ol(?![a-zA-Z])', r'\\overline'), (r'\\dg(?![a-zA-Z])', r'^\\circ'), (r'\\ii(?![a-zA-Z])', r'\\item'),
          (r'\\dang(?![a-zA-Z])', r'\\measuredangle'), (r'\\half(?![a-zA-Z])', r'\\frac12'), (r'\\eps(?![a-zA-Z])', r'\\varepsilon'),
          (r'\\arc(?![a-zA-Z])', r'\\overarc'), (r'\\coloneq(?![a-zA-Z])', ':='), (r'\\ts(?![a-zA-Z])', '')]
SRC.mkdir(parents=True, exist_ok=True)
for y in range(2010, 2027):
    f = SRC / f'JMO-{y}-notes.tex'
    if not f.exists() or f.stat().st_size < 1000:
        subprocess.run(['curl', '-sL', '-A', 'Mozilla/5.0', '-o', str(f), f'https://web.evanchen.cc/exams/JMO-{y}-notes.tex'])
    s = f.read_text()
    m = re.search(r'\\section\{Problems\}(.*?)\\end\{enumerate\}\s*\\pagebreak', s, re.S)
    if not m:
        print('no problems', y); continue
    items = re.split(r'\\item\s*%%\s*Problem\s*(\d+)', m.group(1))
    probs = []
    for k in range(1, len(items), 2):
        t = items[k + 1].strip()
        t = re.sub(r'\n\s*\n+', '\n\n', t)
        for a, b in MACROS:
            t = re.sub(a, b, t)
        probs.append({'label': f'Bài {items[k]}', 'src': t})
    col = {'id': f'oly-usajmo-{y}', 'contest': 'usajmo', 'year': y,
           'title': f'Olympic Toán Hoa Kỳ dành cho THCS (USAJMO) {y}',
           'sourceName': f'USA Junior Mathematical Olympiad {y} (MAA); đề theo bản tổng hợp của Evan Chen',
           'sourceUrl': f'https://web.evanchen.cc/exams/JMO-{y}-notes.pdf',
           'srcNote': 'LaTeX source; macros: \\ZZ=Z, \\RR=R, \\QQ=Q, \\NN=N, \\ol{AB}=segment AB, \\dg=degree, \\ii=\\item, \\dang=directed angle',
           'problems': probs}
    (RAW / f"{col['id']}.json").write_text(json.dumps(col, ensure_ascii=False, indent=1))
    print(y, len(probs))
