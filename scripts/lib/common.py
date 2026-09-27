"""Shared helpers for toanthcs-hard crawlers. Import with sys.path.insert(0, 'scripts/lib')."""
import json, os, re, time, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTENT = ROOT / 'content'
SCRATCH = ROOT / '.cache'
CACHE = SCRATCH / 'gemini'          # Gemini response cache (cache_key -> json)
for d in (CACHE, CONTENT / 'sources', CONTENT / 'theory'):
    d.mkdir(parents=True, exist_ok=True)

TOPICS = ['so-hoc', 'nghiem-nguyen', 'dai-so', 'phuong-trinh', 'bat-dang-thuc', 'hinh-hoc', 'to-hop']
TOPIC_DESC = {
    'so-hoc': 'Số học: chia hết, đồng dư, số nguyên tố, ƯCLN/BCNN, số chính phương, chữ số',
    'nghiem-nguyen': 'Phương trình nghiệm nguyên, phương trình Diophantine',
    'dai-so': 'Biến đổi đại số, hằng đẳng thức, căn thức, đa thức, phân thức, tính giá trị, dãy/tổng',
    'phuong-trinh': 'Phương trình & hệ phương trình khó: vô tỉ, bậc cao, chứa tham số, Vi-ét nâng cao',
    'bat-dang-thuc': 'Bất đẳng thức, cực trị (min/max)',
    'hinh-hoc': 'Hình học phẳng: tam giác, tứ giác, đường tròn, quỹ tích, hình học tổ hợp',
    'to-hop': 'Tổ hợp – rời rạc: Dirichlet, bất biến, cực hạn, đếm, trò chơi, logic, tô màu',
}
LEVEL_DESC = {
    1: 'Đai vàng – khá / nâng cao cơ bản',
    2: 'Đai xanh – giỏi cấp trường/huyện',
    3: 'Đai nâu – HSG tỉnh / câu khó đề chuyên',
    4: 'Đai đen – câu cuối đề chuyên/HSG tỉnh khó, cấp quốc gia/Olympic',
}


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def strip_diacritics(s):
    s = s.replace('đ', 'd').replace('Đ', 'D')
    s = unicodedata.normalize('NFD', s)
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn')


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', strip_diacritics(s).lower()).strip('-')


def write_json_atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp%d' % os.getpid())
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    tmp.rename(path)
