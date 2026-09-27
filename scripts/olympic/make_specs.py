"""Build .cache/olympic/specs.json (inputs for extract.py) from downloaded CJMO / JBMO files."""
import json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
OLY = ROOT / '.cache/olympic'
specs = []
CJMO = {2021: 'https://cms.math.ca/wp-content/uploads/2021/04/CJMO-2021-questions-en.pdf',
        2022: 'https://cms.math.ca/wp-content/uploads/2022/03/2022CJMO_exam_en.pdf',
        2023: 'https://cms.math.ca/wp-content/uploads/2023/03/2023CJMO-exam-en.pdf',
        2024: 'https://cms.math.ca/wp-content/uploads/2024/03/CJMO2024-problems.pdf',
        2025: 'https://cms.math.ca/wp-content/uploads/2025/03/CJMO2025-problems.pdf',
        2026: 'https://cms.math.ca/wp-content/uploads/2026/03/CJMO2026-problems.pdf'}
for y, u in CJMO.items():
    specs.append({'id': f'oly-cjmo-{y}', 'contest': 'cjmo', 'year': y, 'contest_full': 'Canadian Junior Mathematical Olympiad (CJMO)',
                  'title': f'Olympic Toán Canada dành cho THCS (CJMO) {y}',
                  'sourceName': f'Canadian Junior Mathematical Olympiad {y} – Canadian Mathematical Society',
                  'sourceUrl': u, 'files': [str(OLY / f'cjmo/cjmo{y}.pdf')], 'expect': 'The official set has 5 problems.'})
idx = OLY / 'jbmo/index.json'
if idx.exists():
    for e in json.loads(idx.read_text()):
        d = OLY / 'jbmo/files' / e['key']
        files = sorted(str(p) for p in d.glob('*') if p.suffix.lower() in ('.pdf', '.doc', '.docx')) if d.exists() else []
        if not files:
            continue
        y = e['year']
        if e['kind'] == 'jbmo':
            specs.append({'id': f'oly-jbmo-{y}', 'contest': 'jbmo', 'year': y, 'contest_full': 'Junior Balkan Mathematical Olympiad (JBMO), official contest',
                          'title': f'Olympic Toán Balkan dành cho THCS (JBMO) {y}',
                          'sourceName': f'Junior Balkan Mathematical Olympiad {y}; tư liệu tổng hợp bởi pregatirematematicaolimpiadejuniori.wordpress.com',
                          'sourceUrl': e['url'], 'files': files,
                          'note': 'files may also contain solutions, Romanian text, shortlists or other contests; take only the official JBMO contest paper of this year',
                          'expect': 'The official JBMO paper has 4 problems (1997–2023 some years 4 or 5).'})
        else:
            specs.append({'id': f'oly-jbmo-shl-{y}', 'contest': 'jbmo-shl', 'year': y, 'contest_full': 'Junior Balkan Mathematical Olympiad Shortlist (JBMO Shortlist)',
                          'title': f'Danh sách bài đề cử Olympic Toán Balkan dành cho THCS (JBMO Shortlist) {y}',
                          'sourceName': f'JBMO Shortlist {y}; tư liệu tổng hợp bởi pregatirematematicaolimpiadejuniori.wordpress.com',
                          'sourceUrl': e['url'], 'files': files,
                          'note': 'take all shortlisted problems of this year (algebra A, combinatorics C, geometry G, number theory N), not solutions',
                          'expect': 'Use labels like A1, C2, G3, N4.'})
(OLY / 'specs.json').write_text(json.dumps(specs, ensure_ascii=False, indent=1))
print(len(specs))
