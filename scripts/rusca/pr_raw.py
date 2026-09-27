"""problems.ru leaves -> .cache/rusca/raw/ru-<contest>-<year>-...json  (out: olympic-russia)
Usage: python3 scripts/rusca/pr_raw.py [contest ...]   (mmo tot vmo prazdnik ustn67 euler okrug)
Env HIGH=1 also keeps classes 10-11 (grade 10)."""
import json, os, re, html, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
RC = ROOT / '.cache/rusca'
RAW = RC / 'raw'
PR = RC / 'pr'
HIGH = os.environ.get('HIGH') == '1'

NAMES = {
    'mmo': ('Olympic Toán Moskva', 'Московская математическая олимпиада'),
    'tot': ('Giải Toán Các thành phố (Tournament of Towns)', 'Турнир городов'),
    'vmo': ('Olympic Toán toàn Nga', 'Всероссийская олимпиада по математике'),
    'prazdnik': ('Ngày hội Toán học (Moskva)', 'Математический праздник'),
    'ustn67': ('Olympic Toán vấn đáp Moskva lớp 6–7', 'Московская устная олимпиада для 6-7 классов'),
    'euler': ('Olympic Toán Euler (lớp 8, Nga)', 'Олимпиада имени Леонарда Эйлера'),
    'okrug': ('Olympic Toán cấp quận (Moskva)', 'Окружная олимпиада (Москва)'),
}
TR_WORDS = [('подготовительный вариант', 'đề chuẩn bị'), ('первый турнир', 'lần thứ 1'), ('первый тур', 'vòng 1'), ('второй тур', 'vòng 2'), ('для москвичей', 'dành cho học sinh Moskva'), ('основной вариант', 'đề cơ sở'), ('тренировочный вариант', 'đề luyện tập'), ('базовый вариант', 'đề cơ sở'), ('сложный вариант', 'đề nâng cao'), ('класс', 'lớp'), ('классы', 'lớp'), ('тур', 'vòng'), ('Первый день', 'ngày 1'), ('Второй день', 'ngày 2'),
            ('Осенний', 'mùa thu'), ('Весенний', 'mùa xuân'), ('осенний', 'mùa thu'), ('весенний', 'mùa xuân'),
            ('Базовый вариант', 'đề cơ sở'), ('Сложный вариант', 'đề nâng cao'), ('базовый вариант', 'đề cơ sở'), ('сложный вариант', 'đề nâng cao'),
            ('Основной вариант', 'đề cơ sở'), ('Тренировочный вариант', 'đề luyện tập'), ('младшие', 'khối nhỏ'), ('старшие', 'khối lớn'),
            ('Региональный этап', 'vòng khu vực'), ('Заключительный этап', 'vòng chung kết'), ('Окружной этап', 'vòng liên vùng'),
            ('Финальный этап', 'vòng chung kết'), ('Школьный этап', 'vòng trường'), ('Муниципальный этап', 'vòng quận/huyện'),
            ('Всероссийский этап', 'vòng toàn quốc'), ('вариант', 'đề'), ('год', ''), ('Устный тур', 'vòng vấn đáp'),
            ('Письменный тур', 'vòng viết'), ('Региональный', 'khu vực'), ('Заключительный', 'chung kết'), ('этап', 'vòng'),
            ('Дистанционный', 'từ xa'), ('Очный', 'trực tiếp'), ('Командная олимпиада', 'thi đồng đội'), ('задача', 'bài'), ('Задача', 'bài')]


def vi_path(s):
    s = re.sub(r'(\d[\d,\s\-–]*?)\s*класс(?:ы|а|ов)?', lambda m: 'lớp ' + re.sub(r'\s+', '', m.group(1)).replace('-', '–'), s)
    s = re.sub(r'(\d+)\s*турнир\s*\(([^)]*)\)', lambda m: 'lần thứ ' + m.group(1) + ' (năm học ' + m.group(2).replace(' год', '').strip() + ')', s)
    s = re.sub(r'(\d+)\s*тур\b', r'vòng \1', s)
    for a, b in [('осенний тур', 'vòng mùa thu'), ('весенний тур', 'vòng mùa xuân'), ('Осенний тур', 'vòng mùa thu'), ('Весенний тур', 'vòng mùa xuân'), ('устный тур', 'vòng vấn đáp'), ('Устный тур', 'vòng vấn đáp')]:
        s = s.replace(a, b)
    for a, b in TR_WORDS:
        s = re.sub(re.escape(a), b, s, flags=re.I)
    if re.search('[а-яА-Я]', s):
        print('untranslated:', s)
    return re.sub(r'\s+', ' ', s).strip(' ,.')


def clean(h):
    h = re.sub(r'<!--.*?-->', '', h, flags=re.S)
    imgs = []

    def img(m):
        tag = m.group(0)
        alt = re.search(r'ALT="([^"]*)"', tag, re.I)
        if alt and '$' in alt.group(1):
            return ' ' + html.unescape(alt.group(1)).replace('\\displaystyle', '').strip() + ' '
        src = re.search(r'src\s*=\s*"([^"]+)"', tag, re.I)
        if src:
            u = src.group(1)
            u = u if u.startswith('http') else 'https://problems.ru/' + u.lstrip('/')
            imgs.append(u)
            return f' [hình {len(imgs)}] '
        return ' '
    h = re.sub(r'<img[^>]*>', img, h, flags=re.I | re.S)
    h = re.sub(r'<sub>(.*?)</sub>', r'_{\1}', h, flags=re.I | re.S)
    h = re.sub(r'<sup>(.*?)</sup>', r'^{\1}', h, flags=re.I | re.S)
    h = re.sub(r'</?(i|b|tt|em|strong|font|span|nobr|center|a)(\s[^>]*)?>', '', h, flags=re.I)
    h = re.sub(r'<li[^>]*>', '\n- ', h, flags=re.I)
    h = re.sub(r'</t[dh]>', ' | ', h, flags=re.I)
    h = re.sub(r'</?(p|br|div|tr|table|ul|ol)(\s[^>]*)?/?>', '\n', h, flags=re.I)
    h = re.sub(r'<[^>]+>', ' ', h)
    h = html.unescape(h).replace('\xa0', ' ')
    h = re.sub(r'[ \t]+', ' ', h)
    h = re.sub(r' *\n *', '\n', h)
    h = re.sub(r'\n{2,}', '\n\n', h)
    return h.strip(), imgs


def classes_in(s):
    out = set()
    for m in re.finditer(r'(\d{1,2})\s*[-–,]\s*(\d{1,2})\s*класс|(\d{1,2})\s*класс', s, re.I):
        if m.group(3):
            out.add(int(m.group(3)))
        else:
            a, b = int(m.group(1)), int(m.group(2))
            out.update(range(a, b + 1) if b > a and b - a < 5 else (a, b))
    # "7,8 класс"
    m = re.search(r'((?:\d{1,2}\s*,\s*)+\d{1,2})\s*класс', s, re.I)
    if m:
        out.update(int(x) for x in re.findall(r'\d+', m.group(1)))
    return out


def grade_for(key, path, probs):
    txt = ' '.join(path)
    if key == 'prazdnik':
        c = classes_in(txt) or {6, 7}
    elif key == 'ustn67':
        c = classes_in(txt) or {6, 7}
    elif key == 'euler':
        c = {8}
    else:
        c = classes_in(txt)
        if key == 'tot' and not c:
            if re.search(r'младш', txt, re.I):
                c = {8, 9}
            elif re.search(r'старш', txt, re.I):
                c = {10, 11}
        if not c:
            pc = set()
            for p in probs:
                pc.update(int(x) for x in re.findall(r'\d+', p['classes']))
            c = pc
    low = [x for x in c if x <= 9]
    if low:
        return max(6, max(low))
    if HIGH and c:
        return 10
    return None


def main():
    keys = sys.argv[1:] or list(NAMES)
    tot_n = 0
    for key in keys:
        f = PR / f'leaves-{key}.json'
        if not f.exists():
            print('missing', key); continue
        leaves = json.loads(f.read_text())
        groups = {}
        for l in leaves:
            path = l['path']
            ym = re.search(r'(19|20)\d\d', ' '.join(path))
            if not ym or not l['problems']:
                continue
            # group = path without trailing "задача N" nodes
            gp = [x for x in path if not re.match(r'^\s*[Зз]адача\s*\d+', x)]
            groups.setdefault(tuple(gp), []).extend(l['problems'])
        n = 0
        written = set()
        for gp, probs in groups.items():
            grade = grade_for(key, list(gp), probs)
            if grade is None:
                continue
            y = int(re.search(r'(?:19|20)\d\d', ' '.join(gp)).group(0))
            # year of school year like "2010/2011" -> later
            yy = re.findall(r'(?:19|20)\d\d', ' '.join(gp))
            y = max(int(v) for v in yy)
            vi, ru = NAMES[key]
            rest = [vi_path(x) for x in gp if not re.fullmatch(r'\s*(?:19|20)\d\d(\s*[-/]\s*\d+)?\s*год\s*', x)]
            rest = [x for x in rest if x and not re.fullmatch(r'(?:19|20)\d\d.*', x)] or []
            rest = [re.sub(r'^(\d+)\s*\(\s*(?:19|20)\d\d\s*\)$', r'lần thứ \1', x) for x in rest]
            cid = 'ru-' + key + '-' + '-'.join(re.sub(r'[^0-9a-z]+', '-', __import__('unicodedata').normalize('NFD', vi_path(x)).encode('ascii', 'ignore').decode().lower()).strip('-') for x in gp)
            cid = re.sub(r'-+', '-', cid).strip('-')
            items, seen = [], set()
            probs_sorted = sorted(probs, key=lambda p: (int(re.match(r'\d+', p['num']).group(0)) if p['num'] and re.match(r'\d+', p['num']) else 999, p['pid']))
            for k, p in enumerate(probs_sorted):
                num = p['num'] or str(k + 1)
                lab = f'Bài {num}'
                if lab in seen:
                    lab = f'Bài {num} ({p["pid"]})'
                seen.add(lab)
                src, imgs = clean(p['html'])
                if not src:
                    continue
                items.append({'label': lab, 'src': src, 'images': imgs, 'url': f'https://problems.ru/view_problem_details_new.php?id={p["pid"]}'})
            if not items:
                continue
            gtxt = f'lớp {grade}' if grade <= 9 else 'lớp 10–11'
            col = {'id': cid, 'out': 'olympic-russia', 'kind': 'olympic', 'lang': 'ru', 'year': y, 'grade': grade,
                   'title': f'{vi} {y}' + (f' – {", ".join(rest)}' if rest else ''),
                   'sourceName': f'{vi} ({ru}) {y}' + (f', {", ".join(rest)}' if rest else '') + ' – kho đề problems.ru (MCCME)',
                   'sourceUrl': f'https://problems.ru/view_by_source_new.php?parent={next(l["pid"] for l in leaves if tuple(x for x in l["path"] if not re.match(r"^\s*[Зз]адача", x)) == gp)}',
                   'problems': items}
            if cid in written:
                print('DUP', cid)
                cid = cid + '-' + str(len(written))
                col['id'] = cid
            written.add(cid)
            (RAW / f'{cid}.json').write_text(json.dumps(col, ensure_ascii=False, indent=1))
            n += len(items)
        print(key, 'groups', len(groups), 'problems kept', n)
        tot_n += n
    print('total', tot_n)


main()
