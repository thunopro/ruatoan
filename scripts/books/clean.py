"""Clean content/books.json after build.py: drop off-topic entries, unescape titles, add short descs."""
import html, json, os, re
from pathlib import Path
F = Path(__file__).resolve().parents[2] / 'content' / 'books.json'
b = json.loads(F.read_text())
orig, new = b[:45], b[45:]
BAD = re.compile(r'\bvăn\b|tiếng việt|tiếng anh|english|vật lý|vật lí|hóa học|sinh học|lịch sử|địa lí|địa lý|'
                 r'toán\s*[1-5]\b|lớp\s*[1-5]\b|tiểu học|casio|máy tính cầm tay|sgk|sách giáo khoa|sách bài tập toán|'
                 r'^đề |^đề thi|^đề chọn|^đề khảo sát|lượng giác|tích phân|đạo hàm|đường thẳng|mặt phẳng|oxy|thpt|lớp 1[0-2]|toán 1[0-2]', re.I)
NAMES = {'so-hoc': 'số học', 'nghiem-nguyen': 'nghiệm nguyên', 'dai-so': 'đại số', 'phuong-trinh': 'phương trình',
         'bat-dang-thuc': 'bất đẳng thức', 'hinh-hoc': 'hình học', 'to-hop': 'tổ hợp'}
out, drop = [], 0
for x in new:
    x['title'] = html.unescape(x['title']).replace('Sách - ', '').strip()
    if BAD.search(x['title']):
        drop += 1; continue
    g = sorted(x['grades']); gs = 'vào 10 chuyên' if g == [10] else 'lớp ' + '–'.join(map(str, [min(g), max(g)] if len(g) > 1 else g)).replace('10', '9')
    t = ', '.join(dict.fromkeys(NAMES[i] for i in x['topics']))
    lang = {'ru': 'Tiếng Nga. ', 'en': 'Tiếng Anh. '}.get(x['lang'], '')
    kind = 'Tài liệu PDF miễn phí' if x.get('free') else 'Sách in'
    x.setdefault('desc', f'{lang}{kind} về {t}, dành cho {gs}.')
    out.append(x)
tmp = F.with_suffix('.tmp'); tmp.write_text(json.dumps(orig + out, ensure_ascii=False, indent=1)); os.replace(tmp, F)
print('kept', len(out), 'dropped', drop, 'total', len(orig) + len(out))
