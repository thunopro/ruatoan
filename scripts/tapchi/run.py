"""Magazine problems for THCS -> content/sources/tapchi-thtt.json, content/sources/tapchi-ttt.json

Magazines (scanned issues, public Google Drive links listed on the Google Site "Blog Toán" of Lê Trung Kiên):
  thtt : Toán học và Tuổi trẻ  – "Đề ra kì này", only the "Các lớp THCS" problems (T1..T5/<issue>)
  ttt2 : Toán Tuổi thơ 2 (THCS) – "Thi giải toán qua thư" (Bài 1(<issue>) .. Bài 8(<issue>))

Pipeline (resumable, everything cached): download PDF (.cache/tapchi/pdf) -> page thumbnails -> Gemini locates
the section -> hi-res render -> Gemini transcribes the problem statements + topics/level (flash, falls back to
flash-lite) -> KaTeX check + LLM repair -> atomic JSON write (every 5 min and at the end).
Statements only (user decision): no hint/solution/answer. The old "solve" phase (solve.py: solve -> verify-and-fix)
is kept but unused.

  nohup python3 -u scripts/tapchi/run.py extract --mag thtt > .cache/tapchi/extract-thtt.log 2>&1 &
  nohup python3 -u scripts/tapchi/run.py extract --mag ttt2 > .cache/tapchi/extract-ttt2.log 2>&1 &
  python3 scripts/tapchi/run.py assemble --mag thtt,ttt2 [--fix]
Env: GEM (Gemini concurrency; extract default 3, solve default 9), ISSUES (parallel issues, 6), DL (downloads, 3)
"""
import argparse, asyncio, glob, html, json, os, re, subprocess, sys, time, urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONTENT, SCRATCH, log, slug, write_json_atomic  # noqa
from gemini import FLASH, GEMMA, LITE, Gemini, NoCapacity, file_part  # noqa
import solve as S  # noqa

TC = SCRATCH / 'tapchi'
PDF, IMG, STATE = TC / 'pdf', TC / 'img', TC / 'state'
for d in (PDF, IMG, STATE):
    d.mkdir(parents=True, exist_ok=True)

NISS = int(os.environ.get('ISSUES', '6'))
NDL = int(os.environ.get('DL', '3'))
EXTRACT_MODELS = FLASH + LITE[:4]   # transcription: flash-lite is good enough when flash quota is gone

JSON_RULES = ("""- text: chép CHÍNH XÁC đề bài bằng tiếng Việt, MỌI công thức, biến số, tên điểm/đoạn/tam giác (vd $a, b$, $n$, $p$, tam giác $ABC$) đều đặt trong $...$ hoặc $$...$$ bằng LaTeX hợp lệ với KaTeX (không dùng \\( \\) \\[ \\]); số có gạch trên dùng \\overline{abcd}; góc dùng \\widehat{ABC}. Không chép mã bài, tên tác giả vào text. Nếu đề có hình vẽ thì mô tả hình bằng lời (không cần nếu đề đã nói đủ).
- proposer: tên người đề xuất và đơn vị như in bên dưới đề, viết hoa chữ cái đầu mỗi từ (vd "Nguyễn Tấn Ngọc (GV THCS P. Bình Định, An Nhơn, Bình Định)"), rỗng nếu không có.
- complete: false nếu đề bị cắt hoặc có chỗ không đọc được.
- topics: 1–2 mã chủ đề phù hợp nhất:
""" + S.TOPIC_LIST)

MAGS = {
    'thtt': dict(
        name='Toán học và Tuổi trẻ', section='Đề ra kì này',
        level_guide='bài THCS của THTT phần lớn là 3; chỉ bài thật khó cỡ Olympic mới 4; bài lớp 6–7 nhẹ nhàng có thể 2',
        index_url='https://sites.google.com/site/letrungkienmath/bao-toan-hoc-va-tuoi-tre',
        index_file='index_letrungkien.html', out='tapchi-thtt.json',
        loc_prompt="""Trên đây là ảnh thu nhỏ của TẤT CẢ các trang (theo thứ tự "Trang 1", "Trang 2", …) của một số Tạp chí Toán học và Tuổi trẻ (bản scan).
Hãy tìm chuyên mục "ĐỀ RA KÌ NÀY" / "ĐỀ RA KỲ NÀY" (trang đăng đề bài mới của cuộc thi giải toán, các bài có mã như "Bài T1/560", "T2/…", thường chia "Các lớp THCS", "Các lớp THPT"). KHÔNG tính trang "Giải bài kì trước" (lời giải các bài số trước), trang "Problems in this issue" (bản dịch tiếng Anh) hay các đề thi khác.
Trả JSON: pages = danh sách số thứ tự trang (theo nhãn "Trang k" ở trên, KHÔNG phải số in trên trang) chứa phần đề bài của chuyên mục đó (thường 1–2 trang; rỗng nếu không có); issue = số tạp chí in trên bìa/chân trang (vd "560"); month, year = tháng, năm phát hành (0 nếu không đọc được).""",
        ex_prompt="""Các ảnh trên là trang chuyên mục "ĐỀ RA KÌ NÀY" / "ĐỀ RA KỲ NÀY" của Tạp chí Toán học và Tuổi trẻ số {label} (bản scan).
Nhiệm vụ: chép lại TẤT CẢ các đề bài toán mới của chuyên mục này (mã dạng "Bài T1/560", "T7/560", "L1/560"…), gồm mục "Các lớp THCS" / "Dành cho THCS" / "Cấp II", mục "Các lớp THPT" / "Cấp III" và "Tiến tới Olympic Toán". Bỏ qua bài Vật lí (mã L…), bản dịch tiếng Anh, lời giải bài kì trước.
Với mỗi bài:
- code: mã bài như in, dạng "T1/560" (bỏ chữ "Bài"). Nếu mã in không có chữ T (vd "Bài 1/150") thì ghi "1/150".
- section: "THCS" nếu bài thuộc mục dành cho THCS/cấp II/lớp 6–9; "THPT" nếu thuộc mục THPT/cấp III/Tiến tới Olympic toán hoặc không rõ.
- grade_note: vd "Lớp 6" nếu đề ghi "(Lớp 6)", ngược lại rỗng.
- thcs_ok: chỉ quan trọng với bài THPT: true nếu học sinh giỏi THCS (lớp 9 chuyên) giải được bằng kiến thức THCS: số học sơ cấp, phương trình nghiệm nguyên, biến đổi đại số, căn thức, phương trình/hệ đại số, bất đẳng thức đại số sơ cấp (AM-GM, Cauchy-Schwarz), hình học phẳng thuần túy (tam giác, tứ giác, đường tròn), tổ hợp/đếm/Dirichlet/trò chơi. false nếu cần kiến thức THPT: đạo hàm, giới hạn, tích phân, dãy số có giới hạn, hàm số liên tục, lượng giác (hàm sin/cos/tan, phương trình lượng giác, bất đẳng thức lượng giác), mũ/logarit, số phức, vectơ/tọa độ, hình học không gian, tổ hợp chỉnh hợp/nhị thức Newton phức tạp, phương trình hàm trên tập số thực, đa thức cần giải tích. Với bài THCS luôn ghi true.
{rules}
issue/month/year: số báo và tháng, năm phát hành đọc từ chân trang (vd "Số 560 (2-2024)" -> issue "560", month 2, year 2024; 0 nếu không đọc được)."""),
    'ttt2': dict(
        name='Toán Tuổi thơ 2', section='Thi giải toán qua thư',
        level_guide='bài Toán Tuổi thơ phần lớn ở mức 1–3: bài lớp 6–7 thường 1–2, bài lớp 8–9 thường 2–3; chỉ bài cuối thật khó mới 4',
        index_url='https://sites.google.com/site/letrungkienmath/tap-chi-toan-tuoi-tho-2',
        index_file='index_letrungkien_ttt2.html', out='tapchi-ttt.json',
        loc_prompt="""Trên đây là ảnh thu nhỏ của TẤT CẢ các trang (theo thứ tự "Trang 1", "Trang 2", …) của một số Tạp chí Toán Tuổi thơ 2 (THCS, bản scan).
Hãy tìm trang đăng ĐỀ BÀI MỚI của chuyên mục "THI GIẢI TOÁN QUA THƯ" (các bài có mã như "Bài 1(274)", "Bài 2(274)"…, thường có tiêu đề "Các lớp 6 & 7", "Các lớp THCS"). KHÔNG tính các trang lời giải các bài kì trước, danh sách bạn được thưởng, hay các chuyên mục khác.
Trả JSON: pages = danh sách số thứ tự trang (theo nhãn "Trang k" ở trên, KHÔNG phải số in trên trang) chứa các đề bài đó (thường 1 trang; rỗng nếu không có); issue = số tạp chí (vd "274"); month, year = tháng, năm phát hành (0 nếu không đọc được).""",
        ex_prompt="""Các ảnh trên là trang chuyên mục "THI GIẢI TOÁN QUA THƯ" (đề bài kì này) của Tạp chí Toán Tuổi thơ 2 số {label} (bản scan).
Nhiệm vụ: chép lại TẤT CẢ các đề bài mới của chuyên mục này (không chép lời giải bài kì trước nếu có trên trang).
Với mỗi bài:
- code: mã bài như in, dạng "Bài 1(274)".
- grade_note: nhóm lớp theo tiêu đề mục chứa bài: vd "Lớp 6–7" nếu nằm dưới "Các lớp 6 & 7", "Lớp 8–9" nếu dưới "Các lớp 8 & 9"; rỗng nếu tiêu đề là "Các lớp THCS" hoặc không có.
{rules}
issue/month/year: số báo và tháng, năm phát hành (0 nếu không đọc được)."""),
}

LOC_SCHEMA = {'type': 'OBJECT', 'properties': {
    'pages': {'type': 'ARRAY', 'items': {'type': 'INTEGER'}},
    'issue': {'type': 'STRING'}, 'month': {'type': 'INTEGER'}, 'year': {'type': 'INTEGER'}},
    'required': ['pages', 'issue', 'month', 'year']}

EX_SCHEMA = {'type': 'OBJECT', 'properties': {
    'issue': {'type': 'STRING'}, 'month': {'type': 'INTEGER'}, 'year': {'type': 'INTEGER'},
    'problems': {'type': 'ARRAY', 'items': {'type': 'OBJECT', 'properties': {
        'code': {'type': 'STRING'},
        'grade_note': {'type': 'STRING'},
        'section': {'type': 'STRING', 'enum': ['THCS', 'THPT']},
        'thcs_ok': {'type': 'BOOLEAN'},
        'text': {'type': 'STRING'},
        'proposer': {'type': 'STRING'},
        'complete': {'type': 'BOOLEAN'},
        'topics': {'type': 'ARRAY', 'items': {'type': 'STRING', 'enum': S.TOPICS}}},
        'required': ['code', 'grade_note', 'text', 'proposer', 'complete', 'topics'],
        'propertyOrdering': ['code', 'section', 'grade_note', 'thcs_ok', 'text', 'proposer', 'complete', 'topics']}}},
    'required': ['issue', 'month', 'year', 'problems'],
    'propertyOrdering': ['issue', 'month', 'year', 'problems']}


# ---------------------------------------------------------------- index
def load_index(mag):
    cfg = MAGS[mag]
    p = TC / cfg['index_file']
    if not p.exists():
        subprocess.run(['curl', '-sL', '-m', '120', cfg['index_url'], '-o', str(p)], check=True)
    s = p.read_text(errors='ignore')
    issues = {}
    for u, t in re.findall(r'href="([^"]+)"[^>]*>(.*?)</a>', s, flags=re.S):
        u = html.unescape(u)
        t = re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', '', t))).strip()
        if 'google.com/url' in u:
            m = re.search(r'[?&]q=([^&]+)', u)
            if m:
                u = urllib.parse.unquote(m.group(1))
        m = re.search(r'drive\.google\.com/file/d/([\w-]+)', u) or re.search(r'drive\.google\.com/.*[?&]id=([\w-]+)', u)
        if not m:
            continue
        if mag == 'ttt2':
            mm = re.search(r'số\s*(\d+)(?:\s*(?:\+|&|và)\s*(\d+))?', t, flags=re.I)
            if not mm:
                continue
            nums = [x for x in mm.groups() if x]
            ym = re.search(r'năm\s*(\d{4})', t)
            year_hint = int(ym.group(1)) if ym else 0
        else:
            nums = re.findall(r'\d+', t)
            year_hint = 0
        if not nums:
            continue
        key = '-'.join(nums)
        rk = re.search(r'resourcekey=([\w-]+)', u)
        issues[key] = {'mag': mag, 'key': key, 'num': int(nums[0]), 'label': '+'.join(nums), 'fid': m.group(1),
                       'rk': rk.group(1) if rk else None, 'year_hint': year_hint,
                       'url': f'https://drive.google.com/file/d/{m.group(1)}/view' + (f'?resourcekey={rk.group(1)}' if rk else '')}
    return sorted(issues.values(), key=lambda x: -x['num'])


# ---------------------------------------------------------------- download / render
async def run(cmd, timeout=900):
    p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(p.communicate(), timeout)
    except asyncio.TimeoutError:
        p.kill()
        raise RuntimeError('timeout ' + cmd[0])
    return p.returncode, out.decode(errors='ignore'), err.decode(errors='ignore')


def fid(it):
    return f'{it["mag"]}-{it["key"]}'


async def download(it, sem):
    dst = PDF / f'{fid(it)}.pdf'
    if dst.exists() and dst.stat().st_size > 10000:
        return dst
    async with sem:
        for attempt in range(3):
            tmp = dst.with_suffix('.part')
            url = f'https://drive.usercontent.google.com/download?id={it["fid"]}&export=download&confirm=t'
            if it['rk']:
                url += f'&resourcekey={it["rk"]}'
            code, _, _ = await run(['curl', '-sL', '-m', '1500', '-A', 'Mozilla/5.0', url, '-o', str(tmp)], 1600)
            if tmp.exists() and tmp.stat().st_size > 10000 and tmp.read_bytes()[:5] == b'%PDF-':
                tmp.rename(dst)
                return dst
            head = tmp.read_bytes()[:300] if tmp.exists() else b''
            tmp.unlink(missing_ok=True)
            log('download fail', fid(it), code, re.sub(rb'\s+', b' ', head)[:150])
            await asyncio.sleep(60 * (attempt + 1))
    return None


async def thumbs(it, pdf, sem):
    d = IMG / fid(it) / 'thumb'
    if (d / 'done').exists():
        return sorted(glob.glob(str(d / '*.jpg')))
    d.mkdir(parents=True, exist_ok=True)
    async with sem:
        await run(['pdftoppm', '-scale-to', '560', '-gray', '-jpeg', '-jpegopt', 'quality=55', str(pdf), str(d / 'p')], 1200)
    fs = sorted(glob.glob(str(d / '*.jpg')))
    if fs:
        (d / 'done').write_text('1')
    return fs


async def hires(it, pdf, page, sem):
    f = IMG / fid(it) / f'hi-{page:03d}.jpg'
    if f.exists():
        return f
    async with sem:
        await run(['pdftoppm', '-f', str(page), '-l', str(page), '-scale-to', '2000', '-gray', '-jpeg',
                   '-jpegopt', 'quality=80', '-singlefile', str(pdf), str(f.with_suffix(''))], 300)
    return f if f.exists() else None


# ---------------------------------------------------------------- gemini wrapper / state
class G:
    def __init__(self, conc):
        self.g = Gemini(per_slot=2)
        self.sem = asyncio.Semaphore(conc)

    async def gen(self, *a, **kw):
        while True:
            async with self.sem:
                try:
                    return await self.g.generate(*a, **kw)
                except NoCapacity:
                    pass
            log('no gemini capacity for', kw.get('models', [''])[0], '- sleeping 10 min')
            await asyncio.sleep(600)


def state_path(it):
    return STATE / f'{fid(it)}.json'


def load_state(it):
    try:
        return json.loads(state_path(it).read_text())
    except Exception:
        return {}


def save_state(it, st):
    write_json_atomic(state_path(it), st)


# ---------------------------------------------------------------- phase: extract
def norm_code(mag, code, issue_label):
    code = re.sub(r'\s+', ' ', code or '').strip().strip('.:')
    if mag == 'thtt':
        code = re.sub(r'(?i)^bài\s*', '', code).replace(' ', '').upper()
        return code if re.match(r'^T?\d+/\d+$', code) else ''
    m = re.search(r'(\d+)\s*\(\s*([\d+&]+)\s*\)', code)
    if m:
        return f'Bài {m.group(1)}({m.group(2)})'
    m = re.search(r'(\d+)', code)
    return f'Bài {m.group(1)}({issue_label})' if m else ''


async def extract_issue(it, g, sems):
    st = load_state(it)
    if 'problems' in st:
        return
    st.update({k: it[k] for k in ('mag', 'key', 'num', 'label', 'url', 'year_hint')})
    if st.get('status') == 'no-pdf' and st.get('tries', 0) >= 2:
        return
    cfg = MAGS[it['mag']]
    pdf = await download(it, sems['dl'])
    if not pdf:
        st['status'] = 'no-pdf'
        st['tries'] = st.get('tries', 0) + 1
        save_state(it, st)
        return
    th = await thumbs(it, pdf, sems['cpu'])
    if not th:
        st['status'] = 'render-fail'
        save_state(it, st)
        return
    parts = []
    for i, f in enumerate(th):
        parts += [{'text': f'Trang {i + 1}:'}, file_part(f, 'image/jpeg')]
    parts.append({'text': cfg['loc_prompt']})
    r = await g.gen(parts, models=EXTRACT_MODELS, schema=LOC_SCHEMA, cache_key=f'tapchi/{it["mag"]}-loc-v1/{it["key"]}')
    loc = r['result']
    if 'de_ra_pages' in loc:
        loc['pages'] = loc.pop('de_ra_pages')
    pages = sorted({p for p in loc.get('pages') or [] if 1 <= p <= len(th)})[:3]
    st['loc'] = loc
    if not pages:
        st['status'] = 'no-section'
        st['problems'] = []
        save_state(it, st)
        log('no section', fid(it))
        return
    his = [await hires(it, pdf, p, sems['cpu']) for p in pages]
    parts = [file_part(f, 'image/jpeg') for f in his if f]
    parts.append({'text': cfg['ex_prompt'].format(label=it['label'], rules=JSON_RULES)})
    ck = f'tapchi/{it["mag"]}-ex-{"v5" if it["mag"] == "thtt" else "v4"}/{it["key"]}'
    try:
        r = await g.gen(parts, models=EXTRACT_MODELS, schema=EX_SCHEMA, cache_key=ck, temperature=0.2, max_tries=8)
    except RuntimeError as e:   # e.g. RECITATION block -> retry hotter, then gemma
        log('extract retry', fid(it), str(e)[:100])
        try:
            r = await g.gen(parts, models=EXTRACT_MODELS, schema=EX_SCHEMA, cache_key=ck, temperature=1.0, max_tries=6)
        except RuntimeError:
            r = await g.gen(parts, models=GEMMA, schema=EX_SCHEMA, cache_key=ck, temperature=0.7, max_tries=10)
    ex = r['result']
    probs, seen = [], set()
    for p in ex.get('problems') or []:
        code = norm_code(it['mag'], p.get('code'), it['label'])
        if not (p.get('text') or '').strip() or not code or code in seen:
            continue
        seen.add(code)
        topics, _ = S._norm_result(p)
        section = p.get('section') or ('THCS' if it['mag'] == 'ttt2' else 'THPT')
        if it['mag'] == 'thtt' and section == 'THPT' and not p.get('thcs_ok'):
            continue
        probs.append({'code': code, 'section': section, 'grade_note': (p.get('grade_note') or '').strip(),
                      'text': S.repair(p['text']), 'proposer': (p.get('proposer') or '').strip(),
                      'complete': p.get('complete', True), 'topics': topics})
    st['meta'] = {k: ex.get(k) for k in ('issue', 'month', 'year')}
    st['extract_model'] = r.get('model')
    st['problems'] = probs
    st['status'] = 'extracted'
    save_state(it, st)
    log(f'extracted {fid(it)}: {len(probs)} problems {st["meta"]} [{r.get("model")}]')


# ---------------------------------------------------------------- phase: solve
async def solve_problem(g, st_path, code):
    st = json.loads(st_path.read_text())
    p = next(x for x in st['problems'] if x['code'] == code)
    cfg = MAGS[st['mag']]
    key = f'{st["mag"]}-{st["key"]}-{slug(code)}'
    extra = f'(Bài {code} – Tạp chí {cfg["name"]}' + (f', {p["grade_note"]}' if p['grade_note'] else '') + ')'
    res = await S.solve_verify(g.gen, p['text'], key, extra=extra, models=FLASH)
    st = json.loads(st_path.read_text())  # reload: other problems of the issue may have been saved meanwhile
    for x in st['problems']:
        if x['code'] == code:
            x['result'] = res
    write_json_atomic(st_path, st)
    log(f'solved {st_path.stem} {code}: verified={res["verified"]} rounds={res.get("rounds")}')


# ---------------------------------------------------------------- assemble
def fmt_proposer(s):
    s = re.sub(r'\s+', ' ', (s or '').replace('$', '')).strip().strip('.,;')
    if not s:
        return ''
    m = re.match(r'^([^()]*)(.*)$', s)
    name, rest = m.group(1).strip(), m.group(2).strip()
    if name.isupper():
        name = ' '.join(w[:1] + w[1:].lower() for w in name.split())
    return (name + (' ' + rest if rest else '')).strip()


def assemble(mag):
    cfg = MAGS[mag]
    cols = []
    for f in STATE.glob(f'{mag}-*.json'):
        st = json.loads(f.read_text())
        probs = [p for p in st.get('problems') or [] if p.get('complete', True) and p.get('topics')]
        if not probs:
            continue
        meta, loc = st.get('meta') or {}, st.get('loc') or {}
        year = meta.get('year') or loc.get('year') or st.get('year_hint') or 0
        month = meta.get('month') or loc.get('month') or 0
        if not (1960 <= (year or 0) <= 2027):
            year = st.get('year_hint') or 0
        if not (1 <= (month or 0) <= 12):
            month = 0
        if mag == 'thtt' and st['num'] >= 495:   # monthly since no. 495 (09/2018): 559 = 01/2024
            k = 2018 * 12 + 8 + (st['num'] - 495)
            year, month = k // 12, k % 12 + 1
        cid = f'{mag}-{st["key"]}'
        mname = 'Tạp chí ' + cfg['name']
        if mag == 'thtt':
            if st['num'] < 197:   # older issues: bimonthly/irregular, "số k năm Y" is ambiguous -> year only
                month = 0
            when = f'{month}/{year}' if month and year else (str(year) if year else '')
            title = f'{mname} số {st["label"]}' + (f' ({when})' if when else '')
        else:
            when = f'{month:02d}/{year}' if month and year else (str(year) if year else '')
            title = f'{cfg["name"]} số {st["label"]}' + (f' ({when})' if when else '') + f' – {cfg["section"]}'
        items, grades = [], set()
        for p in probs:
            if p.get('section') == 'THPT':
                note = 'Lớp 10'
                grades.add(10)
            else:
                note = p['grade_note']
                gs = [int(x) for x in re.findall(r'\d', note or '') if 6 <= int(x) <= 9]
                grades.add(max(gs) if gs else 9)
            text = (f'*({note})* ' if note else '') + p['text']
            prop = fmt_proposer(p.get('proposer'))
            if mag == 'thtt':
                prop = re.sub(r'\s*\((.*)\)\s*$', r', \1', prop)
                if prop:
                    text += f'\n\n*(Đề xuất: {prop})*'
            else:
                src = f'{cfg["name"]} số {st["label"]}'
                text += f'\n\n*(Đề xuất: {prop} – {src})*' if prop else f'\n\n*({src})*'
            items.append({'id': f'{cid}-{slug(p["code"])}', 'label': p['code'], 'text': text, 'topics': p['topics']})
        items.sort(key=lambda x: [int(n) if n.isdigit() else n for n in re.split(r'(\d+)', x['label'])])
        ids = set()
        items = [x for x in items if not (x['id'] in ids or ids.add(x['id']))]
        grade = 9 if any(g <= 9 for g in grades) else 10
        col = {'id': cid, 'kind': 'tapchi', 'title': title, 'grade': grade}
        if year:
            col['year'] = year
        col.update({'sourceName': f'{mname} số {st["label"]}', 'sourceUrl': st['url'], 'problems': items})
        cols.append((st['num'], col))
    cols = [c for _, c in sorted(cols, key=lambda x: -x[0])]
    pending = S.katex_filter(cols)
    cols = [c for c in cols if c['problems']]
    out = CONTENT / 'sources' / cfg['out']
    try:   # merge: keep collections from other pipelines (not produced from state files)
        old = json.loads(out.read_text())
    except Exception:
        old = []
    mine = {c['id'] for c in cols}
    extra = [c for c in old if c['id'] not in mine and not (STATE / f'{c["id"]}.json').exists()]
    for c in extra:
        for p in c['problems']:
            for k in ('level', 'hint', 'solution', 'answer'):
                p.pop(k, None)
    allc = cols + extra
    num = lambda c: int((re.findall(r'\d+', c['id']) or ['0'])[0])
    allc.sort(key=lambda c: -num(c))
    write_json_atomic(out, allc)
    n = sum(len(c['problems']) for c in allc)
    log(f'assembled {mag}: {len(allc)} issues, {n} problems, {len(pending)} bad latex strings')
    return pending


async def assembler(g, mags, every=300):
    while True:
        await asyncio.sleep(every)
        for m in mags:
            try:
                pending = await asyncio.to_thread(assemble, m)
                await S.fix_pending(g.gen, pending, conc=3)
            except Exception as e:
                log('assemble err', type(e).__name__, e)


# ---------------------------------------------------------------- main
async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('phase', choices=['extract', 'solve', 'assemble'])
    ap.add_argument('--mag', default='thtt')
    ap.add_argument('--from', dest='frm', type=int, default=100000)
    ap.add_argument('--to', type=int, default=0)
    ap.add_argument('--issues', default='')
    ap.add_argument('--fix', action='store_true')
    a = ap.parse_args()
    mags = a.mag.split(',')

    if a.phase == 'assemble':
        g = G(8)
        for m in mags:
            pending = assemble(m)
            if pending and a.fix:
                await S.fix_pending(g.gen, pending, conc=8)
                assemble(m)
        if g.g.session:
            await g.g.session.close()
        return

    if a.phase == 'extract':
        g = G(int(os.environ.get('GEM', '3')))
        idx = [i for m in mags for i in load_index(m)]
        if a.issues:
            want = set(a.issues.split(','))
            idx = [i for i in idx if i['key'] in want or str(i['num']) in want]
        idx = [i for i in idx if a.to <= i['num'] <= a.frm]
        log(f'extract: {len(idx)} issues')
        sems = {'dl': asyncio.Semaphore(NDL), 'cpu': asyncio.Semaphore(3)}
        isem = asyncio.Semaphore(NISS)
        at = asyncio.create_task(assembler(g, mags))
        done = 0

        async def work(it):
            nonlocal done
            async with isem:
                try:
                    await extract_issue(it, g, sems)
                except Exception as e:
                    log('issue err', fid(it), type(e).__name__, str(e)[:200])
            done += 1
            if done % 10 == 0:
                log(f'extract progress {done}/{len(idx)} gemini={g.g.stats}')

        await asyncio.gather(*(work(it) for it in idx))
        at.cancel()
        (TC / f'extract-{"-".join(mags)}.done').write_text(time.strftime('%F %T'))
        for m in mags:
            await S.fix_pending(g.gen, assemble(m))
            assemble(m)
        log('extract done', g.g.stats)
        await g.g.session.close()
        return

    # solve: keep polling state files; newest issues first
    g = G(int(os.environ.get('GEM', '9')))
    at = asyncio.create_task(assembler(g, mags))
    inflight = set()
    sem = asyncio.Semaphore(int(os.environ.get('GEM', '9')) * 2)
    tasks = set()

    async def one(path, code):
        async with sem:
            try:
                await solve_problem(g, path, code)
            except Exception as e:
                log('solve err', path.stem, code, type(e).__name__, str(e)[:200])
                await asyncio.sleep(60)
            finally:
                inflight.discard((path, code))

    idle = 0
    while True:
        todo = []
        for m in mags:
            for f in STATE.glob(f'{m}-*.json'):
                try:
                    st = json.loads(f.read_text())
                except Exception:
                    continue
                if a.to <= st.get('num', 0) <= a.frm:
                    for p in st.get('problems') or []:
                        if p.get('complete', True) and 'result' not in p and (f, p['code']) not in inflight:
                            todo.append((st.get('num', 0), f, p['code']))
        todo.sort(key=lambda x: -x[0])
        for _, f, code in todo[:200]:
            inflight.add((f, code))
            t = asyncio.create_task(one(f, code))
            tasks.add(t)
            t.add_done_callback(tasks.discard)
        extract_done = all((TC / f'extract-{m}.done').exists() for m in mags)
        if not todo and not inflight:
            idle += 1
            if extract_done and idle >= 2:
                break
        else:
            idle = 0
        await asyncio.sleep(60)
    at.cancel()
    for m in mags:
        await S.fix_pending(g.gen, assemble(m))
        assemble(m)
    log('solve done', g.g.stats)
    await g.g.session.close()


if __name__ == '__main__':
    asyncio.run(main())
