"""Shared solve -> verify-and-fix pipeline + LaTeX helpers for magazine problems (THTT, TTT)."""
import asyncio, json, re, subprocess
from pathlib import Path

from common import TOPICS, TOPIC_DESC, LEVEL_DESC, log
from gemini import FLASH, LITE, sha

TOPIC_LIST = '\n'.join(f'- {k}: {v}' for k, v in TOPIC_DESC.items())
LEVEL_LIST = '\n'.join(f'- {k}: {v}' for k, v in LEVEL_DESC.items())
KATEX = Path(__file__).resolve().parents[1] / 'lib' / 'katex_check.mjs'

SOLVE_SCHEMA = {'type': 'OBJECT', 'properties': {
    'topics': {'type': 'ARRAY', 'items': {'type': 'STRING', 'enum': TOPICS}},
    'level': {'type': 'INTEGER'},
    'hint': {'type': 'STRING'},
    'solution': {'type': 'STRING'},
    'answer': {'type': 'STRING'},
    'confident': {'type': 'BOOLEAN'}},
    'required': ['topics', 'level', 'hint', 'solution', 'answer', 'confident'],
    'propertyOrdering': ['topics', 'level', 'hint', 'solution', 'answer', 'confident']}

FORMAT = """Định dạng: tiếng Việt, markdown nhẹ (đoạn cách nhau bằng dòng trống, danh sách dùng "- "), mọi công thức trong $...$ (inline, không xuống dòng bên trong) hoặc $$...$$ (display), LaTeX hợp lệ với KaTeX (\\dfrac, \\sqrt, \\widehat{ABC}, ^\\circ, \\vdots, \\equiv, \\pmod{n}, \\begin{cases}…\\end{cases}); không dùng \\( \\) \\[ \\], không dùng \\text ngoài công thức, không dùng môi trường align (dùng aligned trong $$)."""

SOLVE_PROMPT = """Bạn là chuyên gia bồi dưỡng học sinh giỏi Toán THCS. Hãy giải bài toán sau (bài thi giải toán trên tạp chí, thường khó).

{extra}
ĐỀ BÀI:
{text}

Yêu cầu:
- solution: lời giải ĐẦY ĐỦ, chặt chẽ, trình bày các bước chính, chỉ dùng kiến thức THCS (có thể dùng bất đẳng thức AM-GM/Cauchy-Schwarz, đồng dư, Vi-ét…). Với bài chứng minh: chứng minh trọn vẹn; với bài tìm giá trị: chỉ rõ điều kiện đạt dấu bằng / kiểm tra lại nghiệm; với bài tìm tất cả: chứng minh không còn trường hợp nào khác. Tự kiểm tra lại từng bước trước khi trả lời.
- hint: gợi ý 1–3 câu định hướng ý tưởng chính, KHÔNG lộ đáp số.
- answer: đáp số ngắn gọn (vd "$p = 2$", "$\\max P = 4$ khi $x=y=1$"); với bài chứng minh ghi "Đã chứng minh".
- topics: 1–2 mã chủ đề phù hợp nhất:
{topics}
- level: mức độ khó (thường 3 hoặc 4 với bài tạp chí; 2 nếu khá dễ):
{levels}
- confident: true chỉ khi bạn chắc chắn lời giải hoàn toàn đúng và đầy đủ.
Hãy nháp và kiểm tra trong phần suy nghĩ; solution chỉ chứa bản trình bày cuối cùng gọn gàng như lời giải mẫu (không có câu tự sửa kiểu "xin lỗi, tính lại", không bỏ dở giữa chừng).
{fmt}"""

VERIFY_SCHEMA = {'type': 'OBJECT', 'properties': {
    'errors': {'type': 'STRING', 'description': 'liệt kê các lỗi/lỗ hổng tìm thấy, rỗng nếu không có'},
    'verdict': {'type': 'STRING', 'enum': ['dung', 'sua_duoc', 'sai']},
    'solution': {'type': 'STRING', 'description': 'lời giải hoàn chỉnh đã sửa (bắt buộc nếu verdict=sua_duoc, rỗng nếu dung/sai)'},
    'answer': {'type': 'STRING', 'description': 'đáp số đúng'}},
    'required': ['errors', 'verdict', 'solution', 'answer'],
    'propertyOrdering': ['errors', 'verdict', 'solution', 'answer']}

VERIFY_PROMPT = """Bạn là giám khảo chấm thi học sinh giỏi Toán rất khắt khe. Hãy kiểm tra ĐỘC LẬP lời giải dưới đây.

{extra}
ĐỀ BÀI:
{text}

LỜI GIẢI CẦN KIỂM TRA:
{solution}

ĐÁP SỐ ĐÃ NÊU: {answer}

Cách làm: tự kiểm tra từng bước (tính toán lại, thử lại các giá trị cụ thể, kiểm tra điều kiện dấu bằng, các trường hợp bị bỏ sót, lập luận vòng quanh, khẳng định không được chứng minh). Kiểm tra đáp số bằng cách thử trực tiếp nếu được.
- errors: mô tả ngắn các lỗi tìm thấy.
- verdict = "dung" nếu lời giải đúng, đầy đủ, chặt chẽ (lỗi trình bày rất nhỏ vẫn chấp nhận) VÀ là bản trình bày sạch (không có đoạn nháp, câu tự sửa, hướng làm bị bỏ dở).
- verdict = "sua_duoc" nếu hướng giải đúng nhưng có lỗi/lỗ hổng/đoạn nháp mà bạn sửa được chắc chắn: khi đó viết lại TOÀN BỘ lời giải đã sửa, sạch sẽ vào solution.
- verdict = "sai" nếu hướng giải sai, đáp số sai hoặc có lỗ hổng lớn không sửa được.
- answer: đáp số đúng theo bạn.
{fmt}"""


def _norm_result(r):
    topics = [t for t in dict.fromkeys(r.get('topics') or []) if t in TOPICS][:2] or ['dai-so']
    try:
        lvl = int(r.get('level') or 3)
    except Exception:
        lvl = 3
    return topics, min(4, max(2, lvl))


async def solve_verify(gen, text, key, extra='', models=None, ver='v1'):
    raise RuntimeError('CẤM tạo lời giải/gợi ý/đáp số (quyết định của người dùng). Chỉ chép đề bài.')
    models = models or FLASH
    """Returns {topics, level, hint, solution?, answer?, verified, rounds}."""
    k = sha(text)
    base = None
    r = None
    for rnd in range(2):
        prompt = SOLVE_PROMPT.format(extra=extra, text=text, topics=TOPIC_LIST, levels=LEVEL_LIST, fmt=FORMAT)
        if rnd:
            prompt += '\n\nLưu ý: một lời giải trước đó cho bài này đã bị giám khảo đánh giá là SAI. Hãy giải lại thật cẩn thận theo hướng khác nếu cần.'
        r = await gen([{'text': prompt}], models=models, schema=SOLVE_SCHEMA,
                      cache_key=f'tapchi/solve-{ver}/{key}-{k}-r{rnd}', temperature=None if rnd == 0 else 1.0)
        s = r['result']
        if base is None:
            base = s
        sol, ans = repair(s.get('solution', '')), repair(s.get('answer', ''))
        if not sol.strip():
            continue
        for vr in range(2):
            v = await gen([{'text': VERIFY_PROMPT.format(extra=extra, text=text, solution=sol, answer=ans, fmt=FORMAT)}],
                          models=models, schema=VERIFY_SCHEMA,
                          cache_key=f'tapchi/verify-{ver}/{key}-{sha(sol + ans)}', temperature=0.2)
            vv = v['result']
            verdict = vv.get('verdict')
            if verdict == 'dung':
                topics, lvl = _norm_result(s)
                return {'topics': topics, 'level': lvl, 'hint': repair(s.get('hint', '')), 'solution': sol,
                        'answer': ans or repair(vv.get('answer', '')), 'verified': True, 'rounds': rnd + 1,
                        'model': r.get('model'), 'verifier': v.get('model')}
            if verdict == 'sua_duoc' and (vv.get('solution') or '').strip() and vr == 0:
                sol = repair(vv['solution'])
                ans = repair(vv.get('answer') or ans)
                continue  # re-verify the fixed solution once
            break
    topics, lvl = _norm_result(base or {})
    return {'model': r.get('model') if r else None, 'topics': topics, 'level': lvl, 'hint': repair((base or {}).get('hint', '')), 'verified': False, 'rounds': 2}


# ---------------------------------------------------------------- LaTeX helpers
CTRL = {'\x0c': '\\f', '\t': '\\t', '\x08': '\\b', '\r': '', '\x0b': '\\v', '\x07': '\\a'}


def repair(s):
    s = str(s or '')
    for a, b in CTRL.items():
        s = s.replace(a, b)
    s = s.replace('\\(', '$').replace('\\)', '$')
    s = re.sub(r'\\\[(.+?)\\\]', r'$$\1$$', s, flags=re.S)
    # newline inside inline math -> space
    out, i = [], 0
    for m in re.finditer(r'\$\$[\s\S]+?\$\$|\$([^$]+?)\$', s):
        seg = m.group(0)
        if m.group(1) is not None and '\n' in seg and not re.search(r'\n\s*\n', seg):
            seg = re.sub(r'\s*\n\s*', ' ', seg)
        out.append(s[i:m.start()] + seg)
        i = m.end()
    s = ''.join(out) + s[i:]
    return s.strip()


def katex_check(strings):
    if not strings:
        return []
    p = subprocess.run(['node', str(KATEX)], input=json.dumps(strings), capture_output=True, text=True)
    return json.loads(p.stdout)


FIX_SCHEMA = {'type': 'OBJECT', 'properties': {'fixed': {'type': 'STRING'}}, 'required': ['fixed']}


async def fix_latex(gen, s, err):
    r = await gen([{'text': 'Chuỗi markdown sau có lỗi LaTeX khi render bằng KaTeX (lỗi: ' + err +
                    '). Hãy sửa để mọi công thức nằm trong $...$ (một dòng) hoặc $$...$$ và hợp lệ với KaTeX, '
                    'không có lệnh LaTeX ngoài công thức, giữ nguyên nội dung, không thêm bớt ý. Trả về JSON {"fixed": ...}.\n\n' + s}],
                  models=LITE + FLASH, schema=FIX_SCHEMA, cache_key=f'tapchi/fixtex-v1/{sha(s)}')
    return repair(r['result'].get('fixed', ''))


def cached_fix(s):
    from common import CACHE
    p = CACHE / 'tapchi' / 'fixtex-v1' / (sha(s) + '.json')
    if p.exists():
        try:
            return repair(json.loads(p.read_text())['result'].get('fixed', ''))
        except Exception:
            return None
    return None


def katex_filter(cols):
    """In-place: replace bad strings by cached fixes; drop fields still invalid (drop problem if text invalid).
    Returns list of (string, error) still needing an LLM fix."""
    refs = [(p, f) for c in cols for p in c['problems'] for f in ('text', 'hint', 'solution', 'answer') if p.get(f)]
    errs = katex_check([p[f] for p, f in refs])
    pending = []
    bad = [(p, f, e) for (p, f), e in zip(refs, errs) if e]
    fixes = [(p, f, e, cached_fix(p[f])) for p, f, e in bad]
    cand = [x for x in fixes if x[3]]
    ok2 = katex_check([x[3] for x in cand])
    fixmap = {(id(x[0]), x[1]): x[3] for x, e in zip(cand, ok2) if not e}
    for p, f, e, fx in fixes:
        if (id(p), f) in fixmap:
            p[f] = fixmap[(id(p), f)]
            continue
        pending.append((p[f], e))
        if f == 'text':
            p['_drop'] = True
        elif f == 'solution':
            p.pop('solution', None)
            p.pop('answer', None)
        else:
            p.pop(f, None)
    for c in cols:
        c['problems'] = [p for p in c['problems'] if not p.pop('_drop', False)]
    return pending


async def fix_pending(gen, pending, conc=8):
    sem = asyncio.Semaphore(conc)

    async def one(s, e):
        async with sem:
            try:
                await fix_latex(gen, s, e)
            except Exception as ex:
                log('fixtex fail', type(ex).__name__)

    await asyncio.gather(*(one(s, e) for s, e in pending))


STRONG = set(FLASH)


async def reverify(gen, text, res, key, extra=''):
    raise RuntimeError('CẤM tạo lời giải/gợi ý/đáp số (quyết định của người dùng). Chỉ chép đề bài.')
    """Upgrade a result produced/verified by a weak model: independent FLASH-only verify; if it fails,
    rerun the full solve->verify with FLASH only."""
    if res.get('verified') and res.get('verifier') in STRONG:
        return res
    if res.get('verified'):
        v = await gen([{'text': VERIFY_PROMPT.format(extra=extra, text=text, solution=res['solution'],
                                                     answer=res.get('answer', ''), fmt=FORMAT)}],
                      models=FLASH, schema=VERIFY_SCHEMA,
                      cache_key=f'tapchi/verify-strong/{key}-{sha(res["solution"] + res.get("answer", ""))}',
                      temperature=0.2)
        if v['result'].get('verdict') == 'dung':
            return dict(res, verifier=v.get('model'), weak_solver=True)
    return await solve_verify(gen, text, key, extra, models=FLASH, ver='strong')
