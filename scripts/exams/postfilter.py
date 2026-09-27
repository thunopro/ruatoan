"""Drop non-chuyên mock exams ("cụm chuyên môn") that older catalog versions let into toanmath-chuyen.json."""
import json, os, re
from pathlib import Path
F = Path(__file__).resolve().parents[2] / 'content' / 'sources' / 'toanmath-chuyen.json'
d = json.loads(F.read_text())
keep = [c for c in d if not re.search(r'cụm chuyên môn', c['title'], re.I)]
tmp = F.with_suffix('.tmp'); tmp.write_text(json.dumps(keep, ensure_ascii=False)); os.replace(tmp, F)
print('postfilter: dropped', len(d) - len(keep), 'kept', len(keep))
