"""Filter thcs.toanmath.com posts to advanced topic documents -> .cache/chuyende/docs.json (prints kept list)."""
import html, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from common import SCRATCH, write_json_atomic

POSTS = SCRATCH / 'chuyende' / 'posts.json'
OUT = SCRATCH / 'chuyende' / 'docs.json'
CAT_GRADE = {54: 6, 11: 7, 52: 8, 3: 9, 14: 9, 58: 9}

INCLUDE = re.compile(
    r'bồi dưỡng|học sinh giỏi|\bhsg\b|nâng cao|chuyên toán|toán chuyên|lớp 10 chuyên|olympic|hay và khó|'
    r'đặc sắc|chọn lọc|tuyển chọn|nghiệm nguyên|dirichl|đirichlê|đồng dư|số chính phương|số nguyên tố|'
    r'chia hết|bất đẳng thức|cực trị|gtln|giá trị lớn nhất|vô tỉ|vô tỷ|bất biến|cực hạn|phần nguyên|'
    r'quỹ tích|cố định|thẳng hàng|đồng quy|định lý hình học nổi tiếng|số học|tổ hợp|am – gm|bunyakovski|'
    r'ước và bội|đa thức bồi|đẳng thức hình học|phương trình đại số|biến đổi đại số|hệ phương trình đại số|'
    r'tìm cực trị|diện tích$|min – max|chứng minh vuông góc|chứng minh đẳng thức|hình học phẳng|đặt ẩn phụ|'
    r'tiếp tuyến – cát tuyến|chữ số tận cùng|so sánh|tổng dãy số|khai phóng', re.I)
# routine textbook / worksheet / test material
EXCLUDE = re.compile(
    r'trắc nghiệm|sách giáo khoa|\bsgk\b|kntt|kết nối|cánh diều|chân trời|ctst|phiếu|dạy thêm|học thêm|'
    r'tóm tắt lý thuyết|vở bài tập|vở học sinh|thực tế|xác suất|thống kê|đề kiểm tra|bộ đề|sơ đồ tư duy|'
    r'bất phương trình bậc nhất|cơ bản và nâng cao|từ cơ bản đến nâng cao|chương trình mới|'
    r'tính chất chia hết của một tổng|toàn cảnh đề|phân loại theo chương|phân dạng các bài toán trong đề|'
    r'hệ thống các khái niệm|lời giải bài toán bất đẳng thức, cực trị trong đề|105 bài toán pt|'
    r'hình học trực quan|một số hình phẳng|kinh nghiệm', re.I)
# published books (catalog-only per CONTENT_SPEC) and other manual exclusions
EXCLUDE_IDS = {
    6574, 959,        # Nâng cao và phát triển Toán 8 – Vũ Hữu Bình (sách NXB)
    1337, 1335,       # Bồi dưỡng và phát triển tư duy đột phá Toán 8 (sách)
    5131, 5129,       # Phát triển tư duy sáng tạo giải toán Đại số/Hình học 8 (sách)
    10894,            # Phương pháp Đirichlê và ứng dụng – Nguyễn Hữu Điển (sách NXB GD)
    742,              # Tài liệu chuyên Toán THCS (bộ sách NXB GD)
    7775,             # Bồi dưỡng năng lực và phát triển tư duy học môn Toán 8 (sách)
    14190, 14194, 14192, 14196,  # "khai phóng năng lực" = sách tham khảo theo SGK mới
    7592,             # Chuyên đề so sánh (lớp 6 cơ bản)
    5063,             # phần nguyên — kept via id? (see INCLUDE_IDS)
    14263,            # cẩm nang tra cứu công thức
    5007, 5011, 2029, # routine lớp 9
    1886, 1887, 1888, 1889, 1890, 1891, 1892,  # "Phương pháp giải các dạng toán" SGK cũ lớp 6-7
    4888, 4870, 4842, 11046, 11044, 10995, 4773, 4074, 7641,  # chuyên đề theo bài SGK
    937, 5164, 7331, 3182,  # ôn thi vào 10 đại trà (mức cơ bản)
}
INCLUDE_IDS = {
    5063, 7597, 7590, 7022, 467, 1681, 5156, 11804, 10890, 18824, 5732,
}


def grade_of(title, cat):
    t = title.lower()
    if re.search(r'lớp 10|vào 10|thcs|chuyên toán|toán chuyên', t):
        m = re.search(r'toán ([6-9])\b', t)
        return int(m.group(1)) if m else 9
    m = re.search(r'(?:toán|lớp|học|số học|đại số|hình học)\s*([6-9])\b', t)
    if m:
        return int(m.group(1))
    return CAT_GRADE[cat]


def main():
    posts = json.loads(POSTS.read_text())
    kept = []
    for p in posts:
        title = html.unescape(re.sub(r'<[^>]+>', '', p['title'])).strip()
        ok = (INCLUDE.search(title) and not EXCLUDE.search(title)) or p['id'] in INCLUDE_IDS
        if p['id'] in EXCLUDE_IDS and p['id'] not in INCLUDE_IDS:
            ok = False
        if not ok:
            continue
        pdfs = re.findall(r'href="(https?://[^"]+\.pdf)"', p['content']) or \
            re.findall(r'file=(https?://[^"&]+\.pdf)', p['content'])
        if not pdfs:
            print('NO PDF', p['id'], title)
            continue
        text = html.unescape(re.sub(r'<[^>]+>', ' ', p['content']))
        m = re.search(r'gồm\s+(\d+)\s+trang', text)
        am = re.search(r'biên soạn bởi (?:thầy |cô |tác giả |quý thầy cô )?(?:giáo )?([A-ZÀ-ỸĐ][^,(.;]{3,40}?)(?:\s*\(|,|\.|;| hướng| tuyển| gồm| với)', text)
        author = am.group(1).strip() if am else ''
        if not author:
            m2 = re.search(r'\s[–-]\s([^–-]+)$', title)
            cand = m2.group(1).strip() if m2 else ''
            author = cand if re.fullmatch(r'(?:[A-ZÀ-ỸĐ][a-zà-ỹđ]+\s?){2,4}', cand) else ''
        kept.append({'id': p['id'], 'title': title, 'link': p['link'], 'date': p['date'], 'cat': p['cat'],
                     'grade': grade_of(title, p['cat']), 'pdf': pdfs[0], 'pages': int(m.group(1)) if m else None,
                     'author': author, 'desc': text[:600].strip()})
    kept.sort(key=lambda d: (d['grade'], -d['id']))
    for d in kept:
        print(f"{d['grade']} {d['id']:>5} {str(d['pages']):>4}p  {d['title'][:95]}  | {d['author']}")
    print('kept', len(kept), 'pages', sum(d['pages'] or 0 for d in kept))
    write_json_atomic(OUT, kept)


main()
