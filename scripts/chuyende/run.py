"""Chuyên đề pipeline: select exercise STATEMENTS from thcs.toanmath.com topic PDFs (no hints/solutions).

Per document: PDF (chunked) -> up to ~40 valuable exercises (statement only, self-contained, topics, level)
-> LaTeX repair/KaTeX check -> collection. All Gemini calls disk-cached -> resumable.
Output: content/sources/toanmath-chuyende.json (atomic, rewritten every few documents);
per-doc progress in .cache/chuyende/results.json.

Usage: python3 scripts/chuyende/run.py [--only ID,ID] [--limit N] [--wait] [--redo]
  env CONC (parallel Gemini calls, default 12), DOCS (parallel documents, default 6)
"""
import argparse, asyncio, json, math, os, re, subprocess, sys, time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CACHE, CONTENT, LEVEL_DESC, SCRATCH, TOPIC_DESC, TOPICS, log, slug, write_json_atomic
from gemini import FLASH, GEMMA, LITE, Gemini, NoCapacity, file_part, sha
from texfix import repair

V = 'chuyende-v2'
WORK = SCRATCH / 'chuyende'
PDF = WORK / 'pdf'
SPLIT = WORK / 'split'
OUT = CONTENT / 'sources' / 'toanmath-chuyende.json'
CONC = int(os.environ.get('CONC', '12'))
DOC_CONC = int(os.environ.get('DOCS', '6'))
PER_DOC = 40
CHUNK_PAGES = 60
MAX_CHUNKS = 10
MAX_BYTES = 18_000_000
# statements only: flash-lite lanes are good enough; flash (20 RPD/key/model) only as a last resort
SELECT_MODELS = ['gemini-3.5-flash-lite', 'gemini-3.1-flash-lite', 'gemini-flash-lite-latest',
                 'gemini-3.1-flash-lite-preview', 'gemini-2.5-flash', 'gemini-2.5-flash-lite'] + FLASH

TOPIC_LIST = '\n'.join(f'- {k}: {v}' for k, v in TOPIC_DESC.items())
LEVEL_LIST = '\n'.join(f'- {k}: {v}' for k, v in LEVEL_DESC.items())

FORMAT_RULES = r"""Định dạng mọi chuỗi: tiếng Việt có dấu, markdown nhẹ. Các đoạn cách nhau bằng MỘT DÒNG TRỐNG; danh sách dùng "- " ở đầu dòng.
Công thức toán: LaTeX hợp lệ với KaTeX, inline trong $...$ (KHÔNG được xuống dòng bên trong $...$), công thức dài/hệ/biến đổi nhiều dòng dùng $$...$$ (có thể dùng \begin{aligned}...\end{aligned}, \begin{cases}...\end{cases}).
TUYỆT ĐỐI không dùng \( \) hay \[ \]. Không viết lệnh LaTeX ngoài dấu $. Dùng \dfrac, \sqrt{}, \widehat{ABC}, ^\circ, \Rightarrow, \Leftrightarrow, \vdots (chia hết), \equiv ... \pmod{n}, \ne, \le, \ge."""

SELECT_SCHEMA = {
    'type': 'OBJECT',
    'properties': {
        'topic_name': {'type': 'STRING'},
        'problems': {
            'type': 'ARRAY',
            'items': {
                'type': 'OBJECT',
                'properties': {
                    'src_label': {'type': 'STRING'},
                    'text': {'type': 'STRING'},
                    'topics': {'type': 'ARRAY', 'items': {'type': 'STRING', 'enum': TOPICS}},
                    'level': {'type': 'INTEGER'},
                },
                'required': ['src_label', 'text', 'topics', 'level'],
                'propertyOrdering': ['src_label', 'text', 'topics', 'level'],
            },
        },
    },
    'required': ['topic_name', 'problems'],
    'propertyOrdering': ['topic_name', 'problems'],
}

def select_prompt(doc, k, part):
    return f"""Bạn là giáo viên chuyên Toán THCS nhiều năm bồi dưỡng học sinh giỏi và luyện thi vào lớp 10 chuyên ở Việt Nam.
Tệp PDF đính kèm là {part}tài liệu "{doc['title']}" (đối tượng: học sinh lớp {doc['grade']}{' / ôn thi vào 10 chuyên' if doc['grade'] == 9 else ''}).

NHIỆM VỤ: chọn ra TỐI ĐA {k} bài tập giá trị nhất trong phần tài liệu này để đưa vào kho đề bài nâng cao (chỉ lấy đề bài).

Tiêu chí chọn:
- Ưu tiên bài HAY, KHÓ vừa sức học sinh giỏi, bài KINH ĐIỂN, và ĐA DẠNG dạng toán/phương pháp (mỗi dạng quan trọng trong tài liệu nên có đại diện; không chọn hai bài gần giống nhau).
- Có thể chọn từ phần ví dụ lẫn bài tập tự luyện, bài trích từ đề thi HSG/chuyên.
- BỎ QUA: bài quá dễ/tính toán thuần túy, câu trắc nghiệm, bài phụ thuộc hình vẽ/bảng không thể mô tả bằng lời, bài có đề bị lỗi/thiếu dữ kiện/đọc không rõ, phần lý thuyết.
- Nếu phần tài liệu này không có bài tập phù hợp, trả về danh sách rỗng.

Với mỗi bài:
- src_label: số hiệu bài trong tài liệu (vd "Ví dụ 3", "Bài 15", "Dạng 2 – Bài 4").
- text: CHỈ chép lại ĐỀ BÀI (không chép lời giải, gợi ý hay lý thuyết của tài liệu). Đề phải TỰ ĐỦ NGHĨA: nếu đề dùng giả thiết chung/đề chung của cả nhóm thì chép giả thiết đó vào; nếu bài có nhiều ý a), b), c) thì giữ tất cả các ý trong cùng một đề, mỗi ý một đoạn. Hình vẽ thì mô tả đầy đủ bằng lời. Không chép nguồn đề thi, điểm số. Sửa lỗi chính tả/lỗi đánh máy hiển nhiên.
- topics: 1–2 mã chủ đề phù hợp nhất:
{TOPIC_LIST}
- level: đánh giá TRUNG THỰC theo thang đai (đối chiếu với mặt bằng học sinh cả nước, không phải chỉ so trong tài liệu):
{LEVEL_LIST}
  HIỆU CHỈNH (rất quan trọng, tránh chấm quá cao): PHẦN LỚN bài trong tài liệu chuyên đề là mức 1–2. Mức 1: áp dụng trực tiếp một phương pháp vừa học (vd chứng minh $n^3-n$ chia hết cho 6, tìm $x$ nguyên để phân thức nhận giá trị nguyên, BĐT AM-GM một bước). Mức 2: cần vài bước biến đổi/kết hợp hai ý quen thuộc (vd nghiệm nguyên đưa về tổng bình phương hoặc phương trình ước số, BĐT cần tách/ghép khéo). Mức 3: CHỈ khi bài ngang câu khó đề HSG cấp tỉnh hoặc đề vào 10 chuyên Toán, cần ý tưởng không hiển nhiên. Mức 4: HIẾM, chỉ cho câu cuối đề chuyên Toán/HSG tỉnh rất khó hoặc bài kiểu Olympic/quốc gia. Bài HSG lớp 6–7 hầu như chỉ 1–2, hiếm khi 3.

topic_name: tên chủ đề ngắn gọn của CẢ tài liệu, viết hoa chữ cái đầu, không kèm các từ "Chuyên đề", "bồi dưỡng học sinh giỏi", "ôn thi", "lớp …", tên tác giả (vd "Phương trình nghiệm nguyên", "Số chính phương", "Bất đẳng thức và cực trị hình học", "Đại số nâng cao lớp 9").

{FORMAT_RULES}"""


GEMMA_FIX = GEMMA
FIX_SCHEMA = {'type': 'OBJECT', 'properties': {'fixed': {'type': 'STRING'}}, 'required': ['fixed']}

sem = None
LAT_SEM = None
RESULTS = {}


async def call(g, parts, models, schema, key, temperature=None):
    async with sem:
        return await g.generate(parts, models=models, schema=schema, cache_key=f'{V}/{key}', temperature=temperature)


def katex_check(strings):
    if not strings:
        return []
    p = subprocess.run(['node', str(Path(__file__).resolve().parents[1] / 'lib' / 'katex_check.mjs')],
                       input=json.dumps(strings), capture_output=True, text=True)
    return json.loads(p.stdout)


async def fix_latex(g, s, err):
    """Repair one string with a cheap model; return fixed string or None."""
    try:
        async with LAT_SEM:
            r = await g.generate(
                [{'text': 'Chuỗi markdown sau có lỗi khi render bằng KaTeX (lỗi: ' + err + '). Hãy sửa để mọi công thức '
                  'nằm trong $...$ (không xuống dòng bên trong) hoặc $$...$$ và hợp lệ với KaTeX, không dùng \\( \\) \\[ \\], '
                  'không có lệnh LaTeX ngoài dấu $. Giữ nguyên nội dung và cách trình bày, không thêm bớt ý. '
                  'Trả về JSON {"fixed": ...}.\n\n' + s}],
                models=LITE + GEMMA_FIX, schema=FIX_SCHEMA, cache_key=f'{V}/fixtex/{sha(s + err)}')
        f = repair(r['result']['fixed'])
        if f and not katex_check([f])[0]:
            return f
    except NoCapacity:
        raise
    except Exception as e:
        log('fixtex fail', type(e).__name__)
    return None


# ---------------------------------------------------------------------------------------------------------- PDF
def pdf_pages(path):
    out = subprocess.run(['pdfinfo', str(path)], capture_output=True, text=True).stdout
    return int(re.search(r'Pages:\s+(\d+)', out).group(1))


def make_range(src, a, b, did):
    cp = SPLIT / f'{did}_{a}-{b}.pdf'
    if not cp.exists():
        tmpd = SPLIT / f'tmp_{did}_{a}'
        tmpd.mkdir(parents=True, exist_ok=True)
        subprocess.run(['pdfseparate', '-f', str(a), '-l', str(b), str(src), str(tmpd / 'p%d.pdf')], check=True)
        tmp = cp.with_suffix('.part.pdf')
        subprocess.run(['pdfunite'] + [str(tmpd / f'p{i}.pdf') for i in range(a, b + 1)] + [str(tmp)], check=True)
        tmp.rename(cp)
        for f in tmpd.iterdir():
            f.unlink()
        tmpd.rmdir()
    return cp


def chunks_for(doc):
    src = PDF / f"{doc['id']}.pdf"
    pages = pdf_pages(src)
    size = src.stat().st_size
    n = 1 if pages <= CHUNK_PAGES + 10 else min(MAX_CHUNKS, math.ceil(pages / CHUNK_PAGES))
    n = max(n, math.ceil(size / MAX_BYTES))
    step = math.ceil(pages / n)
    out = []
    for a in range(1, pages + 1, step):
        b = min(pages, a + step - 1)
        if n == 1:
            out.append((src, 1, pages))
        else:
            out.append((make_range(src, a, b, doc['id']), a, b))
    return pages, out


# ---------------------------------------------------------------------------------------------------------- stages
async def select(g, doc):
    pages, chunks = await asyncio.to_thread(chunks_for, doc)
    res = []

    async def one(path, a, b):
        if len(chunks) == 1:
            k, part = PER_DOC, ''
        else:
            k = max(8, round(PER_DOC * (b - a + 1) / pages) + 4)
            part = f'một phần (trang {a}–{b} trên tổng {pages} trang) của '
        parts = [file_part(path, 'application/pdf'), {'text': select_prompt(doc, k, part)}]
        r = await call(g, parts, SELECT_MODELS, SELECT_SCHEMA, f"select/{doc['id']}_{a}-{b}")
        return r['result']

    rs = await asyncio.gather(*(one(*c) for c in chunks), return_exceptions=True)
    for r in rs:
        if isinstance(r, NoCapacity):
            raise r
        if isinstance(r, Exception):
            log('select chunk failed', doc['id'], type(r).__name__, str(r)[:120])
            continue
        res.append(r)
    if not res:
        raise RuntimeError('select failed')
    names = Counter((r.get('topic_name') or '').strip() for r in res if (r.get('topic_name') or '').strip())
    seen, per_chunk = [], []
    for r in res:
        lst = []
        for p in r.get('problems', []):
            if len((p.get('text') or '').strip()) <= 15:
                continue
            t = toks(p['text'])
            if any(jacc(t, x) > 0.8 for x in seen):
                continue
            seen.append(t)
            lst.append(p)
        per_chunk.append(lst)
    # round-robin over chunks so the cap keeps coverage of the whole document
    uniq = []
    while len(uniq) < PER_DOC and any(per_chunk):
        for lst in per_chunk:
            if lst and len(uniq) < PER_DOC:
                uniq.append(lst.pop(0))
    return (names.most_common(1)[0][0] if names else doc['title']), uniq


MATH_RX = re.compile(r'\$\$[\s\S]+?\$\$|\$[^$\n]+?\$')


def outside_math(s, fn):
    out, i = [], 0
    for m in MATH_RX.finditer(s):
        out.append(fn(s[i:m.start()]) + m.group(0))
        i = m.end()
    return ''.join(out) + fn(s[i:])


def pre_clean(s):
    s = repair(s)
    # literal "\n" (escaped newline) left outside math
    s = outside_math(s, lambda t: t.replace('\\n', '\n'))
    return re.sub(r'\n{3,}', '\n\n', s).strip()


async def clean(g, doc, probs):
    for p in probs:
        p['text'] = pre_clean(p.get('text') or '')
    errs = await asyncio.to_thread(katex_check, [p['text'] for p in probs])
    bad = [(p, e) for p, e in zip(probs, errs) if e]
    fixed = await asyncio.gather(*(fix_latex(g, p['text'], e) for p, e in bad))
    dropped = set()
    for (p, e), f in zip(bad, fixed):
        if f:
            p['text'] = f
        else:
            log('  drop (latex):', doc['id'], p['src_label'], e[:80])
            dropped.add(id(p))
    return [p for p in probs if id(p) not in dropped], len(bad)


# ---------------------------------------------------------------------------------------------------------- utils
def toks(s):
    s = re.sub(r'\\[a-zA-Z]+', ' ', s.lower())
    return set(re.findall(r'[0-9a-zà-ỹđ]+', s))


def jacc(a, b):
    return len(a & b) / max(1, len(a | b))


def build_collection(doc, topic_name, probs):
    tn = re.sub(r'^(chuyên đề|chủ đề)\s*:?\s*', '', topic_name.strip(), flags=re.I).strip(' .')
    tn = tn[:1].upper() + tn[1:]
    cid = 'tm-cd-%d-%s' % (doc['id'], '-'.join(slug(tn).split('-')[:6]))
    problems = []
    for p in probs:
        n = len(problems) + 1
        topics = [t for t in dict.fromkeys(p.get('topics') or []) if t in TOPICS][:2] or ['dai-so']
        item = {'id': f'{cid}-{n}', 'label': f'Bài {n}', 'text': p['text'], 'topics': topics,
                'level': min(4, max(1, int(p.get('level') or 2)))}
        problems.append(item)
    return {
        'id': cid, 'kind': 'chuyende', 'title': f'Chuyên đề: {tn} (tuyển chọn)', 'grade': doc['grade'],
        'sourceName': 'toanmath.com' + (f" – {doc['author']}" if doc.get('author') else ''),
        'sourceUrl': doc['link'], 'problems': problems,
    }


def finalize(results, order):
    """Cross-document dedupe, unique titles, atomic write."""
    cols, seen = [], []
    for did in order:
        c = results.get(did)
        if not c:
            continue
        c = json.loads(json.dumps(c))
        keep = []
        for p in c['problems']:
            t = toks(p['text'])
            if len(t) >= 8 and any(jacc(t, s) > 0.85 for s in seen):
                continue
            seen.append(t)
            keep.append(p)
        for i, p in enumerate(keep, 1):
            p['id'] = f"{c['id']}-{i}"
            p['label'] = f'Bài {i}'
        c['problems'] = keep
        if len(keep) >= 3:
            cols.append(c)
    cols.sort(key=lambda c: (c['grade'], c['title']))
    cnt = Counter((c['grade'], c['title']) for c in cols)
    idx = Counter()
    for c in cols:
        k = (c['grade'], c['title'])
        if cnt[k] > 1:
            idx[k] += 1
            au = c['sourceName'].split(' – ', 1)[1] if ' – ' in c['sourceName'] else ''
            c['title'] = c['title'] + (f' – {au}' if au and idx[k] > 1 else (f' ({idx[k]})' if idx[k] > 1 else ''))
    write_json_atomic(OUT, cols)
    return cols


# ---------------------------------------------------------------------------------------------------------- main
async def main():
    global sem, LAT_SEM
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--no-write', action='store_true')
    ap.add_argument('--redo', action='store_true', help='reprocess docs already in results.json')
    ap.add_argument('--wait', action='store_true', help='on quota exhaustion sleep and retry instead of exiting')
    args = ap.parse_args()
    sem = asyncio.Semaphore(CONC)
    LAT_SEM = asyncio.Semaphore(3)
    docs = json.loads((WORK / 'docs.json').read_text())
    docs = [d for d in docs if (PDF / f"{d['id']}.pdf").exists()]
    if args.only:
        ids = {int(x) for x in args.only.split(',')}
        docs = [d for d in docs if d['id'] in ids]
    # small focused documents first; huge compilations last
    docs.sort(key=lambda d: (d.get('pages') or 999, d['id']))
    if args.limit:
        docs = docs[:args.limit]
    order = [d['id'] for d in docs]
    g = Gemini(per_slot=2)
    if args.wait:
        for s_ in g.slots.values():
            s_.day_until = 0
    state_p = WORK / 'results.json'   # per-doc assembled collections (cheap to rebuild from gemini cache)
    try:
        results = {int(k): v for k, v in json.loads(state_p.read_text()).items()}
    except Exception:
        results = {}
    RESULTS.update(results)
    results = RESULTS

    def unmark():
        # shared state file can be stale/over-eager: re-probe day-limited slots (a 429 costs no quota)
        for s in g.slots.values():
            s.day_until = 0
    stats = Counter()
    exhausted = False
    dsem = asyncio.Semaphore(DOC_CONC)
    ndone = 0
    t0 = time.time()

    async def work(doc):
        nonlocal exhausted, ndone
        if exhausted and not args.wait:
            return
        if doc['id'] in results and not args.redo:
            return
        async with dsem:
          while True:
            if exhausted and not args.wait:
                return
            try:
                name, probs = await select(g, doc)
                n_sel = len(probs)
                probs, nbad = await clean(g, doc, probs)
                col = build_collection(doc, name, probs)
                results[doc['id']] = col
                stats['docs'] += 1
                stats['problems'] += len(probs)
                ndone += 1
                log(f"DOC {doc['id']} g{doc['grade']} sel={n_sel} final={len(probs)} latex-bad={nbad} | {col['title']} [{ndone}/{len(docs)} {time.time() - t0:.0f}s] "
                    f"gem={g.stats}")
                if not args.no_write:
                    write_json_atomic(state_p, {str(k): v for k, v in results.items()})
                    if ndone % 3 == 0:
                        finalize(results, [x for x in order] + [k for k in results if k not in order])
                return
            except NoCapacity as e:
                exhausted = True
                log('QUOTA EXHAUSTED', doc['id'], str(e)[:100])
                if not args.wait:
                    return
                await asyncio.sleep(1800)
                unmark()
                exhausted = False
            except Exception as e:
                stats['failed'] += 1
                log('FAILED', doc['id'], type(e).__name__, str(e)[:200])
                return

    await asyncio.gather(*(work(d) for d in docs))
    if g.session:
        await g.session.close()
    g._save_state(force=True)
    all_order = [d['id'] for d in sorted(json.loads((WORK / 'docs.json').read_text()),
                                         key=lambda d: (d.get('pages') or 999, d['id']))]
    if not args.no_write:
        cols = finalize(results, all_order)
        tc, gc = Counter(), Counter()
        for c in cols:
            for p in c['problems']:
                tc[p['topics'][0]] += 1
                gc[(c['grade'], p['level'])] += 1
        log('WROTE', OUT, len(cols), 'collections', sum(len(c['problems']) for c in cols), 'problems')
        log('by topic', dict(tc))
        log('by grade/level', dict(sorted(gc.items())))
    log('END', dict(stats), 'exhausted' if exhausted else 'complete', g.stats)


if __name__ == '__main__':
    asyncio.run(main())
