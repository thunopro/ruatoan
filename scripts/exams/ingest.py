"""Extract structured problem STATEMENTS (label/text/topics/level) from toanmath exam PDFs.

Input : .cache/exams/catalog.json + .cache/pdf/*.pdf   (from scripts/exams/crawl.py)
        .cache/exams/claude/<post_id>-<part>.json      (Claude lane results, see scripts/claude_lane/lane.py)
Output: content/sources/toanmath-hsg.json (kind hsg/olympic, grades 6-9)
        content/sources/toanmath-chuyen.json (kind chuyen, grade 10)
        .cache/exams/ingest_report.json (status, fails, level histogram)

Result sources per exam, in order of preference:
  Gemini Flash (exams-v1 with solutions, exams-v2) > Claude lane > Gemini flash-lite / Gemma (exams-v2-lite, -gemma)
Every Gemini response is cached (.cache/gemini/<version>/...), so a re-run replays finished exams instantly (phase 1)
and then continues with the rest (phase 2). Output files are MERGED with what is already on disk (collections are
replaced per sourceUrl), so --only/--limit runs never shrink the other file. Stops cleanly when all lanes are out
of daily quota.

Usage:
  python3 scripts/exams/ingest.py [--limit N] [--only hsg9,chuyen,hsg8,hsg7,hsg6]
  python3 scripts/exams/ingest.py --write-only     # replay cached + Claude-lane results, write outputs, exit
Env:
  CONC=40            parallel exams (default 40)
  LANES=flash,lite,gemma   model lanes to use, in order (default all three)
"""
import argparse, asyncio, json, os, re, subprocess, sys, time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'lib'))
sys.path.insert(0, str(HERE))
from common import CACHE, CONTENT, SCRATCH, TOPIC_DESC, TOPICS, log, slug, write_json_atomic
from gemini import FLASH, LITE, GEMMA, Gemini, NoCapacity, file_part, sha
from texfix import repair

VERSION = 'exams-v2'                     # statements only
OLD_VERSION = 'exams-v1'                 # first run, had hint/solution/answer (kept if present)
CONC = int(os.environ.get('CONC', '40'))
LANES = [x for x in os.environ.get('LANES', 'flash,lite,gemma').split(',') if x]
OUT = SCRATCH / 'exams'
PDF_DIR = SCRATCH / 'pdf'
SPLIT_DIR = OUT / 'split'
CLAUDE_DIR = OUT / 'claude'
KATEX = HERE.parent / 'lib' / 'katex_check.mjs'
OUT_FILES = {'hsg': CONTENT / 'sources' / 'toanmath-hsg.json', 'chuyen': CONTENT / 'sources' / 'toanmath-chuyen.json'}
MAX_INLINE = 14_000_000
MAX_PAGES = 40

LANE_MODELS = {
    'flash': FLASH,
    'lite': ['gemini-3.5-flash-lite', 'gemini-flash-lite-latest', 'gemini-3.1-flash-lite', 'gemini-3.1-flash-lite-preview'],
    'gemma': GEMMA,
}
LANE_VERSION = {'flash': VERSION, 'lite': VERSION + '-lite', 'gemma': VERSION + '-gemma'}

PROBLEM = {
    'type': 'OBJECT',
    'properties': {
        'label': {'type': 'STRING'},
        'text': {'type': 'STRING'},
        'topics': {'type': 'ARRAY', 'items': {'type': 'STRING', 'enum': TOPICS}},
        'level': {'type': 'INTEGER'},
    },
    'required': ['label', 'text', 'topics', 'level'],
    'propertyOrdering': ['label', 'text', 'topics', 'level'],
}
SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'exams': {
            'type': 'ARRAY',
            'items': {
                'type': 'OBJECT',
                'properties': {
                    'year': {'type': 'INTEGER'},
                    'province': {'type': 'STRING'},
                    'variant': {'type': 'STRING'},
                    'problems': {'type': 'ARRAY', 'items': PROBLEM},
                },
                'required': ['year', 'province', 'variant', 'problems'],
                'propertyOrdering': ['year', 'province', 'variant', 'problems'],
            },
        }
    },
    'required': ['exams'],
}

TOPIC_LIST = '\n'.join(f'   - {k}: {v}' for k, v in TOPIC_DESC.items())

LEVEL_RUBRIC = """   - 1 (Đai vàng): bài nâng cao cơ bản, 1–2 bước quen thuộc — rút gọn biểu thức căn/phân thức, tính giá trị, giải phương trình/hệ quen thuộc, chứng minh tứ giác nội tiếp/tam giác đồng dạng trực tiếp, số học chia hết đơn giản.
   - 2 (Đai xanh): cần một ý tưởng/biến đổi khéo nhưng quen với HSG cấp trường–huyện — đặt ẩn phụ, hằng đẳng thức khéo, phương trình vô tỉ liên hợp cơ bản, BĐT Cô-si/Cauchy–Schwarz một bước, ý hình b/c thông thường, nghiệm nguyên đưa về phương trình ước số.
   - 3 (Đai nâu): mức HSG cấp tỉnh / câu khó đề chuyên — nhiều bước, cần kết hợp kĩ thuật (BĐT có điều kiện, dựng hình phụ, số học đồng dư/chính phương, Dirichlet/bất biến không hiển nhiên).
   - 4 (Đai đen): câu phân loại cuối đề chuyên Toán/HSG tỉnh khó hoặc mức quốc gia/Olympic — rất ít học sinh làm được.
   Ràng buộc: đề cấp trường/huyện/xã/cụm và đề HSG lớp 6–7: đa số ý là 1–2, tối đa 3, KHÔNG có 4. Mỗi đề nhiều nhất 1–2 ý mức 4 (chỉ với đề chuyên/HSG tỉnh). Đề Toán chung (không chuyên): đa số 1–2."""

PROMPT = f"""Bạn là giáo viên chuyên Toán THCS nhiều năm bồi dưỡng học sinh giỏi và luyện thi vào lớp 10 chuyên ở Việt Nam.
Tệp PDF đính kèm là một đề thi (có thể kèm đáp án / hướng dẫn chấm). Thông tin bài đăng gốc:
- Tiêu đề: {{title}}
- Loại: {{kind_desc}}
- Giới thiệu: {{intro}}

NHIỆM VỤ: chép lại TOÀN BỘ các bài/câu/ý của đề thành danh sách bài toán có cấu trúc. KHÔNG giải, không viết gợi ý hay lời giải.

QUY TẮC
1. Tách theo từng ý nhỏ: "Bài 1a", "Bài 1b", "Câu 2.1", "Câu 5"… (label theo đúng cách đánh số của đề). Câu trắc nghiệm: mỗi câu một bài, label "Câu 3 (trắc nghiệm)", text gồm cả các phương án A, B, C, D (mỗi phương án một dòng riêng).
2. text: chép CHÍNH XÁC từng kí hiệu của đề bài bằng tiếng Việt (đọc kĩ số mũ, chỉ số, dấu, biểu thức dưới căn; không để trống đối số như \\sqrt{{}}). Mỗi ý phải TỰ ĐỦ NGHĨA: nếu ý b, c dùng chung giả thiết/biểu thức/hình vẽ thì chép lại toàn bộ phần giả thiết chung ở đầu text của từng ý (giống hệt nhau giữa các ý). Chép ĐỦ mọi dữ kiện và yêu cầu cụ thể của ý (vd các biến cố cần tính xác suất; bảng số liệu dạng bảng markdown `| … |`), không kết thúc text bằng dấu ":" mà thiếu nội dung. Hình vẽ trong đề: mô tả bằng lời đủ để giải. Không chép điểm số, "Hết", ghi chú giám thị, số báo danh, không chép phần đáp án/hướng dẫn chấm.
3. topics: 1–2 mã chủ đề phù hợp nhất:
{TOPIC_LIST}
4. level (1–4), chấm TRUNG THỰC theo độ khó thực tế của chính ý đó so với mặt bằng học sinh giỏi cả nước:
{LEVEL_RUBRIC}
5. Định dạng: markdown nhẹ (đoạn cách nhau bằng dòng trống, danh sách bằng "- "). Mọi công thức, kể cả biến đơn lẻ, đặt trong $...$ (inline, không xuống dòng bên trong) hoặc $$...$$ (display). TUYỆT ĐỐI không dùng \\( \\) hay \\[ \\]. LaTeX phải hợp lệ với KaTeX: \\sqrt{{x}}, \\dfrac{{a}}{{b}}, \\widehat{{ABC}}, ^\\circ, \\Rightarrow, \\begin{{cases}}…\\end{{cases}}, \\overset{{\\frown}}{{AB}}, \\vdots (chia hết), \\equiv, \\pmod{{n}}. Không dùng lệnh LaTeX hay kí hiệu toán Unicode (√ ≥ ≤ ≠ ∈ π) ngoài $.
6. year: năm diễn ra kì thi (đề "năm học 2024 – 2025" thi khoảng tháng 3/2025 → 2025; nếu phần giới thiệu nêu ngày thi thì lấy năm của ngày đó; đề vào lớp 10 năm học 2025 – 2026 → 2025). province: tỉnh/thành phố có dấu (vd "Nghệ An", "Hà Nội", "TP. Hồ Chí Minh"); đề toàn quốc/không rõ thì chuỗi rỗng. variant: ghi chú phân biệt nếu tệp có nhiều đề (vd "Vòng 2", "Đề chung", "Bảng A"), bình thường để rỗng.
7. Nếu tệp chứa NHIỀU đề khác nhau (nhiều vòng/nhiều lớp/nhiều năm), mỗi đề là một phần tử trong "exams". Bình thường chỉ có 1 đề. Nếu tệp chỉ có đáp án mà không có đề bài thì trả về "exams": [] .
8. Tiếng Việt tự nhiên, đúng chính tả, có dấu.
"""

KIND_DESC = {
    'hsg': 'đề thi chọn học sinh giỏi môn Toán lớp {g}',
    'olympic': 'đề thi Olympic / giao lưu học sinh giỏi môn Toán lớp {g}',
    'chuyen': 'đề thi tuyển sinh vào lớp 10 chuyên (môn Toán chuyên hoặc Toán chung cho thí sinh thi chuyên)',
}

FIX_SCHEMA = {'type': 'OBJECT', 'properties': {'fixed': {'type': 'STRING'}}, 'required': ['fixed']}

# LaTeX that renders but is certainly a transcription error
EMPTY_ARG = re.compile(r'\\(?:sqrt|d?frac|tfrac|widehat|overline|vec)\s*(?:\[[^\]]*\])?\s*\{\s*\}|\\d?frac\{[^{}]*\}\{\s*\}|[\^_]\{\s*\}')


class QuotaOut(Exception):
    pass


# ---------------------------------------------------------------------------------------------------------- catalog
def entry_key(e):
    return f'{e["post_id"]}-{e["part"]}'


def title_years(t):
    return [int(y) for y in re.findall(r'\b(20[0-3]\d|19\d\d)\b', t)]


def group_of(e):
    return 'chuyen' if e['kind'] == 'chuyen' else f'hsg{e["grade"]}'


def priority(e):
    ys = title_years(e['title'])
    y = max(ys) if ys else 0
    tier = 0 if group_of(e) in ('hsg9', 'chuyen') else {'hsg8': 1, 'hsg7': 2, 'hsg6': 3}[group_of(e)]
    return (tier, -y, -e['post_id'])


def scope_of(e):
    """'low' for school/district/commune/cluster papers, 'chung' for Toán chung, else 'high'."""
    t = e['title'].lower()
    if e['kind'] == 'chuyen':
        return 'chung' if re.search(r'không chuyên|\(chung|đề chung|toán chung', t) else 'high'
    if re.search(r'trường thcs|phòng gd|huyện|quận|thị xã|thành phố thuộc|cấp xã|\bxã\b|cụm|cấp trường|liên trường|'
                 r'trường|thcs', t) and not re.search(r'sở gd|cấp tỉnh|chuyên', t):
        return 'low'
    return 'high'


def pdf_pages(path):
    try:
        out = subprocess.run(['pdfinfo', str(path)], capture_output=True, text=True, timeout=60).stdout
        return int(re.search(r'Pages:\s+(\d+)', out).group(1))
    except Exception:
        return 0


def prepare_pdf(e):
    """Return path of the PDF to send (truncated to MAX_PAGES / size limit when needed), or None."""
    src = PDF_DIR / e['pdf_file']
    if not src.exists() or src.stat().st_size < 1000:
        return None
    pages = pdf_pages(src)
    if src.stat().st_size <= MAX_INLINE and pages <= MAX_PAGES:
        return src
    SPLIT_DIR.mkdir(parents=True, exist_ok=True)
    n = min(pages or MAX_PAGES, MAX_PAGES)
    while n >= 2:
        dst = SPLIT_DIR / f'{src.stem}_1-{n}.pdf'
        if not dst.exists():
            tmpd = SPLIT_DIR / f'tmp_{src.stem}'
            tmpd.mkdir(exist_ok=True)
            subprocess.run(['pdfseparate', '-f', '1', '-l', str(n), str(src), str(tmpd / 'p%d.pdf')], check=True)
            subprocess.run(['pdfunite'] + [str(tmpd / f'p{i}.pdf') for i in range(1, n + 1)] + [str(dst)], check=True)
            for f in tmpd.iterdir():
                f.unlink()
            tmpd.rmdir()
        if dst.stat().st_size <= MAX_INLINE:
            return dst
        n //= 2
    return None


# ---------------------------------------------------------------------------------------------------------- latex
def katex_check(strings):
    if not strings:
        return []
    p = subprocess.run(['node', str(KATEX)], input=json.dumps(strings), capture_output=True, text=True)
    errs = json.loads(p.stdout)
    return [e or ('empty argument: ' + m.group(0) if (m := EMPTY_ARG.search(s)) else None) for s, e in zip(strings, errs)]


async def fix_strings(g, problems, allow_model=True):
    """Deterministic repair, then a cheap Gemini fix for strings that still fail KaTeX; drop what can't be fixed.
    Problems whose text has an empty LaTeX argument are marked _empty (transcription error, needs re-extraction)."""
    refs = [(p, f) for p in problems for f in ('text', 'hint', 'solution', 'answer') if p.get(f)]
    for p, f in refs:
        p[f] = repair(p[f])
    errs = await asyncio.to_thread(katex_check, [p[f] for p, f in refs])
    bad = [(p, f, e) for (p, f), e in zip(refs, errs) if e]
    for p, f, e in bad:
        if e.startswith('empty argument'):
            p['_empty'] = True
    bad = [b for b in bad if not b[2].startswith('empty argument')]

    async def one(p, f, e):
        if not allow_model:
            return None
        prompt = ('Chuỗi markdown sau có lỗi LaTeX khi render bằng KaTeX (lỗi: ' + e + '). Hãy sửa để mọi công thức '
                  'nằm trong $...$ (inline, không xuống dòng bên trong) hoặc $$...$$ và hợp lệ với KaTeX; không dùng \\( \\) '
                  '\\[ \\]; không để lệnh LaTeX ngoài $. Giữ nguyên nội dung, không thêm bớt ý. Trả về JSON {"fixed": ...}.\n\n'
                  + p[f])
        try:
            r = await g.generate([{'text': prompt}], models=LANE_MODELS['lite'] + FLASH, schema=FIX_SCHEMA,
                                 cache_key=f'exams-v1-fixtex/{sha(p[f])}', max_tries=12)
            return repair(r['result'].get('fixed') or '') or None
        except NoCapacity:
            pass
        except Exception as ex:
            log('fixtex fail', type(ex).__name__, str(ex)[:100])
        return None

    fixed = await asyncio.gather(*(one(*b) for b in bad))
    cand = [(b, s) for b, s in zip(bad, fixed) if s]
    ok = set()
    if cand:
        errs2 = await asyncio.to_thread(katex_check, [s for _, s in cand])
        for ((p, f, e), s), e2 in zip(cand, errs2):
            if not e2:
                p[f] = s
                ok.add((id(p), f))
    dropped = 0
    for p, f, e in bad:
        if (id(p), f) not in ok:
            if f == 'text':
                p['_bad'] = True
            else:
                p.pop(f, None)
            dropped += 1
    return len(bad), dropped


# ---------------------------------------------------------------------------------------------------------- results
def claude_path(e, ext):
    return CLAUDE_DIR / f'{entry_key(e)}.{ext}'


def claude_busy(e):
    """Claimed / done / skipped by the Claude lane -> never send to Gemini."""
    return any(claude_path(e, x).exists() for x in ('claim', 'json', 'skip'))


def _cache_file(version, e):
    stem = e['pdf_file'].removesuffix('.pdf')
    d = CACHE / version
    if not d.exists():
        return None
    pat = re.compile(re.escape(stem) + r'_[0-9a-f]{24}(-retry)?\.json')
    hits = sorted((f for f in d.glob(re.sub(r'([*?\[])', r'[\1]', stem) + '_*.json') if pat.fullmatch(f.name)),
                  key=lambda f: ('-retry' not in f.name, f.stat().st_mtime))  # prefer retry (re-extraction)
    return hits[0] if hits else None


def cached_result(e):
    """Best available result without calling a model: Flash > Claude lane > lite/Gemma."""
    order = [OLD_VERSION, VERSION, 'claude', LANE_VERSION['lite'], LANE_VERSION['gemma'], OLD_VERSION + '-lite']
    for v in order:
        f = claude_path(e, 'json') if v == 'claude' else _cache_file(v, e)
        if f and f.exists():
            try:
                r = json.loads(f.read_text())
                r.setdefault('model', v)
                r['_src'] = v
                return r
            except Exception:
                pass
    return None


def mark_gemini_done(e):
    """lane.py treats an exam as done when a file named <stem>_* exists in .cache/gemini/exams-v1."""
    d = CACHE / OLD_VERSION
    d.mkdir(parents=True, exist_ok=True)
    (d / f'{e["pdf_file"].removesuffix(".pdf")}_v2done').touch()


def make_prompt(e, retry_note=''):
    return (PROMPT.replace('{title}', e['title']).replace('{kind_desc}', KIND_DESC[e['kind']].format(g=e['grade']))
            .replace('{intro}', e.get('intro', '')[:500]) + retry_note)


async def extract(g, e, retry_note=''):
    pdf = await asyncio.to_thread(prepare_pdf, e)
    if pdf is None:
        return None
    name = f'{e["pdf_file"].removesuffix(".pdf")}_{sha(pdf.read_bytes())}' + ('-retry' if retry_note else '')
    parts = [file_part(pdf, 'application/pdf'), {'text': make_prompt(e, retry_note)}]
    for lane in LANES:
        try:
            r = await g.generate(parts, models=LANE_MODELS[lane], schema=SCHEMA,
                                 cache_key=f'{LANE_VERSION[lane]}/{name}', temperature=0.2, max_tries=8)
            r['_src'] = LANE_VERSION[lane]
            return r
        except NoCapacity:
            continue
    raise QuotaOut()


PROV_FIX = {'TP HCM': 'TP. Hồ Chí Minh', 'TP. HCM': 'TP. Hồ Chí Minh', 'Hồ Chí Minh': 'TP. Hồ Chí Minh',
            'TP Hồ Chí Minh': 'TP. Hồ Chí Minh', 'Thành phố Hồ Chí Minh': 'TP. Hồ Chí Minh', 'BR VT': 'Bà Rịa – Vũng Tàu',
            'Bà Rịa - Vũng Tàu': 'Bà Rịa – Vũng Tàu', 'TT Huế': 'Thừa Thiên Huế', 'Huế': 'Thừa Thiên Huế',
            'Thành phố Hà Nội': 'Hà Nội', 'TP. Hà Nội': 'Hà Nội'}


def norm_province(p, title):
    p = (p or '').strip()
    if not re.match(r'(?i)tp\.?\s*(hcm|hồ)', p):
        p = re.sub(r'^(tỉnh|thành phố|tp\.?)\s+', '', p, flags=re.I)
    if not p:
        m = re.search(r'\s[–-]\s([^–-]+)$', title)
        p = m.group(1).strip() if m else ''
    return PROV_FIX.get(p, p) or None


def calibrate_levels(e, probs):
    """Deterministic cap: school/district papers and HSG 6-7 max level 3; Toán chung max 3; at most 2 level-4 per paper."""
    scope = scope_of(e)
    cap = 3 if scope in ('low', 'chung') or (e['kind'] == 'hsg' and e['grade'] <= 7) else 4
    for p in probs:
        p['level'] = min(p['level'], cap)
    fours = [p for p in probs if p['level'] == 4]
    for p in fours[:-2]:
        p['level'] = 3


def build_collections(e, r):
    """Result -> list of Collection dicts (without KaTeX repair)."""
    exams = [x for x in (r['result'].get('exams') or []) if x.get('problems')]
    cols = []
    base_slug = re.sub(r'\.html$', '', e['link'].rstrip('/').rsplit('/', 1)[1])
    base_slug = re.sub(r'^(de-thi-|de-)', '', base_slug)
    prefix = 'tm-chuyen' if e['kind'] == 'chuyen' else f'tm-hsg{e["grade"]}'
    base_slug = re.sub(r'^(chon-)?(hsg|hoc-sinh-gioi|tuyen-sinh|olympic)-', '', base_slug)[:70].strip('-')
    title = re.sub(r'\s+-\s+', ' – ', e['title'])
    ty = title_years(e['title'])
    for i, x in enumerate(exams):
        try:
            year = int(x.get('year') or 0)
        except Exception:
            year = 0
        if ty and not (min(ty) - 1 <= year <= max(ty) + 1):
            year = max(ty) if e['kind'] != 'chuyen' else min(ty)
        cid = f'{prefix}-{base_slug}' + (f'-p{e["part"] + 1}' if e['part'] else '') + (f'-{i + 1}' if i else '')
        t = title
        v = (x.get('variant') or '').strip()
        if len(exams) > 1 and v and v.lower() not in t.lower():
            t += f' ({v})'
        elif len(exams) > 1:
            t += f' (đề {i + 1})'
        seen = Counter()
        probs = []
        for p in x['problems']:
            text = (p.get('text') or '').strip()
            if not text:
                continue
            lab = (p.get('label') or '').strip() or f'Câu {len(probs) + 1}'
            ps = slug(re.sub(r'^(bài|bai|câu|cau)\s*', '', lab, flags=re.I)) or str(len(probs) + 1)
            seen[ps] += 1
            if seen[ps] > 1:
                ps += f'-{seen[ps]}'
            topics = [tp for tp in dict.fromkeys(p.get('topics') or []) if tp in TOPICS][:2] or ['dai-so']
            try:
                lvl = min(4, max(1, int(p.get('level') or 2)))
            except Exception:
                lvl = 2
            item = {'id': f'{cid}-{ps}', 'label': lab, 'text': text, 'topics': topics, 'level': lvl}
            # Statements only: hint/solution/answer are never copied (user ban on solutions).
            probs.append(item)
        if not probs:
            continue
        calibrate_levels(e, probs)
        col = {'id': cid, 'kind': e['kind'], 'title': t, 'grade': e['grade']}
        if year:
            col['year'] = year
        prov = norm_province(x.get('province'), e['title'])
        if prov:
            col['province'] = prov
        col.update(sourceName='toanmath.com', sourceUrl=e['link'], problems=probs)
        cols.append(col)
    return cols


def toks(col):
    s = ' '.join(p['text'] for p in col['problems'])
    return set(re.sub(r'[^0-9a-zà-ỹđ]+', ' ', s.lower()).split())


def dedupe(cols):
    groups = defaultdict(list)
    for c in cols:
        groups[(c['kind'] == 'chuyen', c['grade'], c.get('year'))].append(c)
    out, ndup = [], 0
    for cs in groups.values():
        cs.sort(key=lambda c: (-len(c['problems']), -sum(len(p.get('solution', '')) for p in c['problems']), c['id']))
        kept = []
        for c in cs:
            t = toks(c)
            if any(len(t & kt) / max(1, min(len(t), len(kt))) > 0.75 and abs(len(t) - len(kt)) < 0.5 * max(len(t), len(kt))
                   for _, kt in kept):
                ndup += 1
                continue
            kept.append((c, t))
        out += [c for c, _ in kept]
    return out, ndup


def write_outputs(done_cols, run_urls):
    """Merge this run's collections into the files on disk: collections whose sourceUrl was (re)built in this run are
    replaced, everything else on disk is kept."""
    new = [c for cs in done_cols.values() for c in cs]
    if not new:
        return {}, 0
    new_urls = {c['sourceUrl'] for c in new}
    old = []
    for path in OUT_FILES.values():
        try:
            old += [c for c in json.loads(path.read_text()) if c.get('sourceUrl') not in new_urls]
        except Exception:
            pass
    cols, ndup = dedupe(old + new)
    ids = Counter()
    for c in cols:  # guarantee unique ids
        ids[c['id']] += 1
        if ids[c['id']] > 1:
            base = c['id']
            c['id'] = f'{base}-{ids[base]}'
            for p in c['problems']:
                p['id'] = c['id'] + p['id'][len(base):]
    stats = {}
    for name, path in OUT_FILES.items():
        sel = [c for c in cols if (c['kind'] == 'chuyen') == (name == 'chuyen')]
        sel.sort(key=lambda c: (-c['grade'], -(c.get('year') or 0), c['title']))
        write_json_atomic(path, sel)
        stats[name] = (len(sel), sum(len(c['problems']) for c in sel))
    return stats, ndup


def level_histogram():
    h = defaultdict(Counter)
    for path in OUT_FILES.values():
        try:
            for c in json.loads(path.read_text()):
                for p in c['problems']:
                    h[f'{c["kind"]}{c["grade"]}'][p['level']] += 1
        except Exception:
            pass
    return {k: dict(sorted(v.items())) for k, v in sorted(h.items())}


# ---------------------------------------------------------------------------------------------------------- main
async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--only', default='')
    ap.add_argument('--write-only', '--cached-only', dest='write_only', action='store_true')
    args = ap.parse_args()

    catalog = json.loads((OUT / 'catalog.json').read_text())
    catalog = [e for e in catalog if not e.get('pdf_missing')]
    if args.only:
        catalog = [e for e in catalog if group_of(e) in args.only.split(',')]
    catalog.sort(key=priority)
    if args.limit:
        catalog = catalog[:args.limit]

    g = Gemini(per_slot=1)
    sem = asyncio.Semaphore(CONC)
    done_cols, done_src = {}, {}
    status, fails = Counter(), {}
    stop = asyncio.Event()
    since_write = 0
    write_lock = asyncio.Lock()
    t0 = time.time()
    replay = [True]

    async def flush(force=False):
        nonlocal since_write
        async with write_lock:
            if replay[0] or (not force and since_write < 20):
                return
            since_write = 0
            stats, ndup = await asyncio.to_thread(write_outputs, done_cols, None)
            src = Counter(done_src.values())
            log(f'WROTE {stats} dups={ndup} status={dict(status)} src={dict(src)} gemini={g.stats}')

    async def finish(e, r, allow_retry):
        """Result -> repaired collections; re-extract once (Gemini) if statements contain empty LaTeX args."""
        cols = build_collections(e, r)
        nbad = ndrop = nempty = 0
        for c in cols:
            b, d = await fix_strings(g, c['problems'], allow_model=True)
            nbad += b
            ndrop += d
            nempty += sum(1 for p in c['problems'] if p.get('_empty'))
        if nempty and allow_retry and r.get('_src') != 'claude':
            try:
                r2 = await extract(g, e, retry_note='\nLƯU Ý: lần trích xuất trước có công thức bị trống đối số (vd \\sqrt{}). '
                                                   'Hãy đọc thật kĩ và chép đầy đủ mọi biểu thức.')
                if r2:
                    return await finish(e, r2, False)
            except QuotaOut:
                pass
        for c in cols:
            c['problems'] = [p for p in c['problems'] if not p.pop('_bad', False) and not p.pop('_empty', False)]
        cols = [c for c in cols if c['problems']]
        return cols, r, nbad, ndrop, nempty

    async def work(e, use_cache_only):
        nonlocal since_write
        if stop.is_set():
            return
        async with sem:
            if stop.is_set():
                return
            k = entry_key(e)
            claimed = False
            try:
                r = cached_result(e)
                if r is None:
                    if use_cache_only:
                        status['uncached'] += 1
                        return
                    if claude_busy(e):
                        status['claude_busy'] += 1
                        return
                    try:  # claim so the Claude lane does not pick it up while Gemini works on it
                        CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
                        fd = os.open(claude_path(e, 'claim'), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                        os.write(fd, b'gemini-ingest')
                        os.close(fd)
                        claimed = True
                    except FileExistsError:
                        status['claude_busy'] += 1
                        return
                    r = await extract(g, e)
                    if r is None:
                        status['no_pdf'] += 1
                        return
                    mark_gemini_done(e)
                cols, r, nbad, ndrop, nempty = await finish(e, r, allow_retry=not use_cache_only)
                if not cols:
                    status['empty'] += 1
                    if not use_cache_only:
                        log('empty', e['title'][:80])
                    return
                done_cols[k] = cols
                done_src[k] = r.get('_src')
                status['ok'] += 1
                since_write += 1
                if not use_cache_only:
                    n = sum(len(c['problems']) for c in cols)
                    lv = Counter(p['level'] for c in cols for p in c['problems'])
                    log(f'ok [{group_of(e)}] {e["title"][:60]} -> {len(cols)} col, {n} probs, L{dict(sorted(lv.items()))}, '
                        f'tex bad {nbad} drop {ndrop} empty {nempty} ({r.get("model")})')
            except QuotaOut:
                if not stop.is_set():
                    log('daily quota exhausted on all lanes -> stopping cleanly')
                stop.set()
                status['quota'] += 1
                return
            except Exception as ex:
                status['fail'] += 1
                fails[k] = f'{type(ex).__name__}: {str(ex)[:200]}'
                log('FAIL', e['title'][:70], fails[k])
            finally:
                if claimed:
                    claude_path(e, 'claim').unlink(missing_ok=True)
        await flush()

    # phase 1: replay everything already available (Gemini cache + Claude lane), write once
    await asyncio.gather(*(work(e, True) for e in catalog))
    replay[0] = False
    status.pop('uncached', None)
    log(f'replayed {len(done_cols)} cached exams')
    await flush(force=True)
    if not args.write_only:
        # phase 2: the rest; loop so exams released by the Claude lane get picked up later
        for rnd in range(3):
            todo = [e for e in catalog if entry_key(e) not in done_cols and entry_key(e) not in fails]
            if not todo or stop.is_set():
                break
            status.pop('claude_busy', None)
            await asyncio.gather(*(work(e, False) for e in todo))
            await flush(force=True)
    left = [entry_key(e) for e in catalog if entry_key(e) not in done_cols]
    report = {'status': dict(status), 'src': dict(Counter(done_src.values())), 'fails': fails, 'left': len(left),
              'levels': level_histogram(), 'gemini': g.stats, 'seconds': int(time.time() - t0)}
    write_json_atomic(OUT / ('write_report.json' if args.write_only else 'ingest_report.json'), report)
    log('DONE' if not stop.is_set() else 'STOPPED (quota)', dict(status), 'left', len(left), 'levels', report['levels'])
    if g.session:
        await g.session.close()


if __name__ == '__main__':
    asyncio.run(main())
