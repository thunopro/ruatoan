"""Translate Russian/English problem statements (Kvant, problems.ru, Crux, CEMC) to Vietnamese, filter THCS-suitable ones,
then build content/sources/<out>.json.  STATEMENTS ONLY (no hint/solution/answer/level).

Input : .cache/rusca/raw/<collection-id>.json  {id, out, kind, title, grade, year, sourceName, sourceUrl, lang,
                                               problems:[{label, src, proposer?, images?:[url|path]}]}
Cache : .cache/rusca/tr/<collection-id>.json   {label: {ok, text, topics, proposer, model}}
Output: content/sources/<out>.json

Usage : nohup python3 scripts/rusca/translate.py [id-prefix ...] > .cache/rusca/translate.log 2>&1 &
        python3 scripts/rusca/translate.py --build
"""
import asyncio, hashlib, json, re, subprocess, sys, time
from pathlib import Path
import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from common import log, slug, write_json_atomic, ROOT, CONTENT
from gemini import Gemini, FLASH, LITE, NoCapacity, sha, file_part

RC = ROOT / '.cache/rusca'
RAW = RC / 'raw'
TR = RC / 'tr'
IMG = RC / 'img'
for d in (TR, IMG):
    d.mkdir(parents=True, exist_ok=True)
KATEX = ROOT / 'scripts/lib/katex_check.mjs'
MODELS = ['gemini-3.5-flash-lite'] + FLASH + ['gemini-3.1-flash-lite', 'gemini-flash-lite-latest', 'gemini-3.1-flash-lite-preview', 'gemini-2.5-flash-lite', 'gemma-4-26b-a4b-it', 'gemma-4-31b-it']
V = 'rc1'
TOPICS5 = ['so-hoc', 'dai-so', 'bat-dang-thuc', 'hinh-hoc', 'to-hop']
TOPIC_TXT = '''- so-hoc: số học, chia hết, đồng dư, số nguyên tố, chữ số, phương trình nghiệm nguyên
- dai-so: biến đổi đại số, đa thức, phương trình/hệ phương trình, dãy số, hàm số đơn giản
- bat-dang-thuc: bất đẳng thức, cực trị (min/max)
- hinh-hoc: hình học phẳng, dựng hình, quỹ tích, hình học tổ hợp
- to-hop: tổ hợp – rời rạc, đếm, Dirichlet, bất biến, trò chơi, logic, tô màu, bảng ô vuông, đồ thị'''
STYLE = (
    'Quy ước trình bày: tiếng Việt tự nhiên, dùng thuật ngữ toán THCS Việt Nam (ví dụ "chứng minh rằng", "số nguyên dương", '
    '"tam giác nhọn", "đường tròn ngoại tiếp", "trung điểm"). Công thức dùng $...$ (inline, không xuống dòng bên trong) hoặc $$...$$; '
    'tuyệt đối không dùng \\( \\) \\[ \\]; không để lệnh LaTeX ngoài dấu $; chỉ dùng lệnh KaTeX chuẩn (\\overline, ^\\circ, '
    '\\angle, \\mathbb{Z}, \\le, \\ge, \\cdot). Đoạn cách nhau một dòng trống; các ý a), b) mỗi ý một đoạn riêng; '
    'không dùng tiêu đề markdown, không in đậm tiêu đề.')

SCHEMA = {'type': 'object', 'properties': {'items': {'type': 'array', 'items': {'type': 'object', 'properties': {
    'label': {'type': 'string'},
    'suitable': {'type': 'boolean'},
    'text': {'type': 'string'},
    'topics': {'type': 'array', 'items': {'type': 'string', 'enum': TOPICS5}},
    'proposer': {'type': 'string'}}, 'required': ['label', 'suitable', 'text', 'topics', 'proposer']}}}, 'required': ['items']}
FIX_SCHEMA = {'type': 'object', 'properties': {'fixed': {'type': 'string'}}, 'required': ['fixed']}

LANG = {'ru': 'tiếng Nga', 'en': 'tiếng Anh'}


def prompt_for(col, probs):
    body = '\n\n'.join(
        f'### {p["label"]}\n{p["src"]}' + (f'\n[Người đề xuất: {p["proposer"]}]' if p.get('proposer') else '')
        + (f'\n[Kèm {len(p["_imgs"])} hình vẽ của bài này, theo thứ tự ảnh đính kèm]' if p.get('_imgs') else '')
        for p in probs)
    return (
        f'Các bài toán sau ({LANG.get(col.get("lang"), "tiếng nước ngoài")}) lấy từ: {col["sourceName"]}.\n'
        'Mục tiêu: kho đề nâng cao cho học sinh giỏi THCS Việt Nam (lớp 6–9, thi vào lớp 10 chuyên). CHỈ ĐỀ BÀI.\n'
        'Với MỖI bài (giữ nguyên label), trả về:\n'
        '- suitable: CHỈ phân loại theo chủ đề/kiến thức và lớp học nhìn thấy trực tiếp trong đề (KHÔNG giải, KHÔNG thử giải, KHÔNG kiểm tra tính giải được). '
        'true nếu đề thuộc các mảng THCS: số học, đại số sơ cấp, phương trình, bất đẳng thức, hình học phẳng, tổ hợp, trò chơi, logic. '
        'false nếu đề nhắc tới/thuộc mảng: giới hạn, đạo hàm, tích phân, số phức, lượng giác (sin, cos, tan, phương trình lượng giác), '
        'hình học không gian/hình khối (hình chóp, mặt cầu, hình lập phương 3 chiều...), vectơ, ma trận, xác suất liên tục, toán cao cấp; '
        'hoặc là bài vật lý; hoặc đề phụ thuộc hình vẽ không có; hoặc đề thiếu dữ kiện/không tự đủ nghĩa (ví dụ "như bài trước"). Nếu false thì text để rỗng.\n'
        '- text: bản dịch tiếng Việt chính xác, đầy đủ mọi giả thiết và câu hỏi, tự đủ nghĩa; không thêm gợi ý, không đáp số, không lời giải, không cách làm, '
        'không đổi dữ kiện; nếu có hình vẽ thì mô tả bằng lời những gì cần thiết (không ghi "xem hình"). Không ghi tên người đề xuất trong text.\n'
        '- topics: 1–2 chủ đề (chủ đề chính trước) trong:\n' + TOPIC_TXT + '\n'
        '- proposer: tên người đề xuất/tác giả viết bằng chữ Latinh (phiên âm tên Nga sang Latinh, ví dụ "С. Литовченко" → "S. Litovchenko"; '
        'giữ nguyên nơi/chức danh nếu có, dịch sang tiếng Việt, ví dụ "học sinh lớp 10"); rỗng nếu không có.\n'
        + STYLE + '\n\nĐỀ GỐC:\n' + body)


def katex_check(strings):
    if not strings:
        return []
    r = subprocess.run(['node', str(KATEX)], input=json.dumps(strings), capture_output=True, text=True, cwd=ROOT)
    return json.loads(r.stdout)


def repair(s):
    s = (s or '').strip()
    s = re.sub(r'\\\[(.+?)\\\]', lambda m: '$$' + m.group(1) + '$$', s, flags=re.S)
    s = re.sub(r'\\\((.+?)\\\)', lambda m: '$' + m.group(1) + '$', s, flags=re.S)
    s = s.replace('\\dg', '^\\circ').replace('\\ZZ', '\\mathbb{Z}').replace('\\RR', '\\mathbb{R}')
    s = s.replace('\\QQ', '\\mathbb{Q}').replace('\\NN', '\\mathbb{N}')
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s


async def fix_text(g, s):
    for rnd in range(3):
        err = (await asyncio.to_thread(katex_check, [s]))[0]
        if not err:
            return s
        prompt = ('Chuỗi markdown sau có lỗi khi render KaTeX (lỗi: ' + err + '). Sửa để mọi công thức nằm trong $...$ '
                  '(inline, không xuống dòng bên trong) hoặc $$...$$ và hợp lệ với KaTeX; không dùng \\( \\) \\[ \\]; '
                  'không để lệnh LaTeX ngoài $. Giữ nguyên nội dung. Trả về JSON {"fixed": ...}.\n\n' + s)
        try:
            r = await g.generate([{'text': prompt}], models=MODELS, schema=FIX_SCHEMA,
                                 cache_key=f'rc-fixtex/{sha(s)}-{rnd}', max_tries=12)
            if r['result'].get('fixed'):
                s = repair(r['result']['fixed'])
        except Exception as ex:
            log('fixtex fail', type(ex).__name__)
    return None


MIME = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/png', '.webp': 'image/webp'}


async def get_img(sess, url):
    if not url.startswith('http'):
        return Path(url)
    ext = Path(url.split('?')[0]).suffix.lower()
    if ext not in MIME:
        ext = '.img'
    p = IMG / (hashlib.sha1(url.encode()).hexdigest()[:20] + ext)
    if not p.exists():
        for t in range(3):
            try:
                async with sess.get(url) as r:
                    b = await r.read()
                    ct = r.headers.get('content-type', '')
                if r.status == 200 and b:
                    p.write_bytes(b)
                    break
            except Exception:
                await asyncio.sleep(2)
    if not p.exists():
        return None
    # normalise gif / unknown -> png
    if ext in ('.gif', '.img'):
        png = p.with_suffix('.png')
        if not png.exists():
            try:
                from PIL import Image
                im = Image.open(p)
                im.seek(0)
                im.convert('RGBA' if im.mode in ('P', 'RGBA', 'LA') else 'RGB').save(png)
            except Exception:
                return None
        return png if png.exists() else None
    return p


async def do_col(g, col, sess):
    out = TR / f'{col["id"]}.json'
    done = json.loads(out.read_text()) if out.exists() else {}
    todo = [p for p in col['problems'] if p['label'] not in done]
    if not todo:
        return done
    # attach images
    for p in todo:
        paths = []
        for u in (p.get('images') or [])[:4]:
            ip = await get_img(sess, u)
            if ip:
                paths.append(ip)
        p['_imgs'] = paths
    i = 0
    while i < len(todo):
        chunk, nimg = [], 0
        while i < len(todo) and len(chunk) < 5 and nimg + len(todo[i]['_imgs']) <= 8:
            chunk.append(todo[i]); nimg += len(todo[i]['_imgs']); i += 1
        if not chunk:
            chunk = [todo[i]]; i += 1
        pr = prompt_for(col, chunk)
        parts = []
        for p in chunk:
            for ip in p['_imgs']:
                parts.append(file_part(ip, MIME.get(ip.suffix.lower(), 'image/png')))
        parts.append({'text': pr})
        try:
            r = await g.generate(parts, models=MODELS, schema=SCHEMA,
                                 cache_key=f'rc-{V}/{col["id"]}-{sha(pr + str([str(x) for p in chunk for x in p["_imgs"]]))}',
                                 temperature=0.2, max_tries=30)
        except NoCapacity as e:
            log('no capacity', col['id'], e); raise
        except Exception as e:
            log('fail', col['id'], str(e)[:200]); continue
        got = {str(it.get('label', '')).strip(): it for it in r['result'].get('items', [])}
        for p in chunk:
            it = got.get(p['label'])
            if not it:
                log('missing', col['id'], p['label']); continue
            if not it.get('suitable') or not (it.get('text') or '').strip():
                done[p['label']] = {'ok': False, 'model': r['model']}
                continue
            text = await fix_text(g, repair(it['text']))
            if not text:
                log('bad tex', col['id'], p['label']); continue
            topics = [t for t in it.get('topics', []) if t in TOPICS5][:2] or ['to-hop']
            done[p['label']] = {'ok': True, 'text': text, 'topics': topics,
                                'proposer': (it.get('proposer') or '').strip(), 'model': r['model']}
        write_json_atomic(out, done)
    log('col', col['id'], f'{sum(1 for v in done.values() if v.get("ok"))} ok / {len(done)} done / {len(col["problems"])}')
    return done


def split_parts(text):
    # put sub-items a) b) c) on their own paragraphs (outside math only)
    segs = re.split(r'(\$\$.+?\$\$|\$[^$\n]+?\$)', text, flags=re.S)
    for i in range(0, len(segs), 2):
        segs[i] = re.sub(r'(?<=[.?!:;])[ \t]+(\(?[a-eа-д]\))[ \t]', r'\n\n\1 ', segs[i])
    out = ''.join(segs)
    return re.sub(r'\n{3,}', '\n\n', out)


def build():
    by = {}
    for f in sorted(RAW.glob('*.json')):
        col = json.loads(f.read_text())
        by.setdefault(col['out'], [])
        tp = TR / f.name
        if not tp.exists():
            continue
        done = json.loads(tp.read_text())
        probs, seen = [], set()
        for p in col['problems']:
            t = done.get(p['label'])
            if not t or not t.get('ok'):
                continue
            pid = f'{col["id"]}-{slug(p["label"])}'
            if pid in seen:
                continue
            seen.add(pid)
            text = split_parts(t['text'])
            prop = t.get('proposer', '').strip().strip('.').strip() if p.get('proposer') else ''
            if prop and not re.search(r'[\$\\]', prop):
                text += f'\n\n*(Đề xuất: {prop})*'
            label = p['label']
            m = re.match(r'^(.*\D)\s+(\d+)$', label)
            if m and len(label) > 14:
                label = f'Bài {m.group(2)}'
                text = f'*(Trích từ: {m.group(1).strip()})*\n\n' + text
            probs.append({'id': pid, 'label': label, 'text': text, 'topics': t['topics']})
        if not probs:
            continue
        c = {'id': col['id'], 'kind': col['kind'], 'title': col['title'], 'grade': col['grade']}
        if col.get('year'):
            c['year'] = col['year']
        c.update(sourceName=col['sourceName'], sourceUrl=col['sourceUrl'], problems=probs)
        by[col['out']].append(c)
    stats = {}
    for fname, cols in by.items():
        if not cols:
            continue
        cols.sort(key=lambda c: (-(c.get('year') or 0), c['id']))
        write_json_atomic(CONTENT / 'sources' / f'{fname}.json', cols)
        stats[fname] = (len(cols), sum(len(c['problems']) for c in cols))
    log('build', stats)


async def main():
    args = sys.argv[1:]
    if args == ['--build']:
        build(); return
    cols = [json.loads(f.read_text()) for f in sorted(RAW.glob('*.json'))]
    if args:
        cols = [c for c in cols if any(c['id'].startswith(a) for a in args)]
    g = Gemini(per_slot=2)
    sem = asyncio.Semaphore(12)
    last = [0]
    stop = [False]

    async with aiohttp.ClientSession(headers={'User-Agent': 'Mozilla/5.0'}, timeout=aiohttp.ClientTimeout(total=60)) as sess:
        async def one(col):
            if stop[0]:
                return
            async with sem:
                if stop[0]:
                    return
                try:
                    await do_col(g, col, sess)
                except NoCapacity:
                    stop[0] = True
                    return
            if time.time() - last[0] > 30:
                last[0] = time.time(); build()

        await asyncio.gather(*(one(c) for c in cols))
    build()
    log('stats', g.stats, 'stopped(no capacity)' if stop[0] else '')
    if g.session:
        await g.session.close()


if __name__ == '__main__':
    asyncio.run(main())
