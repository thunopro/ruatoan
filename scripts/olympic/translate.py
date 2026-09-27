"""Translate olympiad problem statements to Vietnamese (+ topics, level), then build content/sources/olympic-*.json.
(Per user decision: statements only — no hint/solution/answer.)

Input : .cache/olympic/raw/<collection-id>.json   (from raw_*.py / extract.py)
Cache : .cache/olympic/tr/<collection-id>.json     (per collection: {label: record}, resumable)
Output: content/sources/olympic-<contest>.json     (rebuilt after every finished collection)

Usage : nohup python3 scripts/olympic/translate.py [collection-id-prefix ...] > .cache/olympic/translate.log 2>&1 &
        python3 scripts/olympic/translate.py --build
"""
import asyncio, json, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from common import log, slug, write_json_atomic, ROOT, CONTENT, TOPICS, TOPIC_DESC, LEVEL_DESC
from gemini import Gemini, FLASH, LITE, NoCapacity, sha

OLY = ROOT / '.cache/olympic'
RAW = OLY / 'raw'
TR = OLY / 'tr'
TR.mkdir(parents=True, exist_ok=True)
KATEX = ROOT / 'scripts/lib/katex_check.mjs'
MODELS = LITE[:4] + FLASH
V = 'tr1'

# contest -> (output file, grade)
CONTESTS = {
    'jbmo': ('olympic-jbmo', 9), 'jbmo-shl': ('olympic-jbmo-shortlist', 9),
    'usajmo': ('olympic-usajmo', 9), 'cjmo': ('olympic-cjmo', 9),
    'sharygin': ('olympic-sharygin', 9), 'mmo': ('olympic-moscow', 9), 'tot': ('olympic-tournament-of-towns', 9),
    'vmo-ru': ('olympic-russia', 9), 'homc': ('olympic-homc', 9),
}

TOPIC_TXT = '\n'.join(f'- {k}: {v}' for k, v in TOPIC_DESC.items())
LEVEL_TXT = '\n'.join(f'- {k}: {v}' for k, v in LEVEL_DESC.items())
STYLE = (
    'Quy ước: tiếng Việt tự nhiên, thuật ngữ toán THCS Việt Nam. Công thức dùng $...$ (inline, không xuống dòng bên trong) '
    'hoặc $$...$$; tuyệt đối không dùng \\( \\) \\[ \\]; không để lệnh LaTeX ngoài dấu $; chỉ dùng lệnh KaTeX hỗ trợ '
    '(không \\dang, \\ol, \\dg, \\ZZ, \\RR, \\ii; dùng \\overline, ^\\circ, \\mathbb{Z}, \\angle). Đoạn cách nhau một dòng trống; '
    'danh sách dùng "- " đầu dòng; không dùng tiêu đề markdown.')

SCHEMA = {'type': 'object', 'properties': {'items': {'type': 'array', 'items': {'type': 'object', 'properties': {
    'label': {'type': 'string'},
    'text': {'type': 'string'},
    'topics': {'type': 'array', 'items': {'type': 'string', 'enum': TOPICS}},
    'level': {'type': 'integer'}}, 'required': ['label', 'text', 'topics', 'level']}}}, 'required': ['items']}
FIX_SCHEMA = {'type': 'object', 'properties': {'fixed': {'type': 'string'}}, 'required': ['fixed']}


def prompt_for(col, probs):
    body = '\n\n'.join(f'### {p["label"]}\n{p["src"]}' for p in probs)
    return (
        f'Các bài toán sau thuộc kì thi "{col["title"]}".\n'
        f'{("Ghi chú nguồn: " + col["srcNote"] + chr(10)) if col.get("srcNote") else ""}'
        'Với MỖI bài (giữ nguyên label), trả về:\n'
        '- text: bản dịch tiếng Việt chính xác, đầy đủ mọi giả thiết và câu hỏi, tự đủ nghĩa; không thêm gợi ý, không lời giải, '
        'không đổi dữ kiện; nếu đề có hình vẽ thì mô tả bằng lời những gì cần thiết.\n'
        f'- topics: 1–2 chủ đề trong:\n{TOPIC_TXT}\n'
        f'- level: 3 hoặc 4 theo thang:\n{LEVEL_TXT}\n(Bài dễ của kì thi Olympic dành cho THCS là 3; bài khó/cuối đề là 4.)\n'
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
                                 cache_key=f'oly-fixtex/{sha(s)}-{rnd}', max_tries=12)
            if r['result'].get('fixed'):
                s = repair(r['result']['fixed'])
        except Exception as ex:
            log('fixtex fail', type(ex).__name__)
    return None


async def do_col(g, col):
    out = TR / f'{col["id"]}.json'
    done = json.loads(out.read_text()) if out.exists() else {}
    todo = [p for p in col['problems'] if p['label'] not in done]
    if not todo:
        return done
    for i in range(0, len(todo), 8):
        chunk = todo[i:i + 8]
        pr = prompt_for(col, chunk)
        try:
            r = await g.generate([{'text': pr}], models=MODELS, schema=SCHEMA, cache_key=f'oly-{V}/{col["id"]}-{sha(pr)}',
                                 temperature=0.2, max_tries=12)
        except NoCapacity as e:
            log('no capacity', col['id'], e); return done
        except Exception as e:
            log('fail', col['id'], str(e)[:200]); continue
        got = {it['label'].strip(): it for it in r['result'].get('items', [])}
        for p in chunk:
            it = got.get(p['label'])
            if not it:
                log('missing', col['id'], p['label']); continue
            text = await fix_text(g, repair(it['text']))
            if not text:
                log('bad tex', col['id'], p['label']); continue
            topics = [t for t in it.get('topics', []) if t in TOPICS][:2] or ['to-hop']
            level = it.get('level') if it.get('level') in (3, 4) else (4 if (it.get('level') or 0) > 4 else 3)
            done[p['label']] = {'text': text, 'topics': topics, 'level': level, 'model': r['model']}
        write_json_atomic(out, done)
    log('col', col['id'], f'{len(done)}/{len(col["problems"])}')
    return done


def label_vi(label):
    l = label.strip()
    m = re.fullmatch(r'(?:Problem|Bài|Задача|P|J)\s*\.?\s*(\d+[a-z]?)\.?', l, re.I)
    if m:
        return f'Bài {m.group(1)}'
    return l if l.lower().startswith('bài') else f'Bài {l}'


def build():
    by = {}
    n = 0
    for f in sorted(RAW.glob('*.json')):
        col = json.loads(f.read_text())
        tp = TR / f.name
        if not tp.exists():
            continue
        done = json.loads(tp.read_text())
        probs, seen = [], set()
        for p in col['problems']:
            t = done.get(p['label'])
            if not t:
                continue
            lab = label_vi(p['label'])
            pid = f'{col["id"]}-{slug(lab)}'
            if pid in seen:
                continue
            seen.add(pid)
            probs.append({'id': pid, 'label': lab, 'text': t['text'], 'topics': t['topics'], 'level': t['level']})
        if not probs:
            continue
        fname, grade = CONTESTS[col['contest']]
        c = {'id': col['id'], 'kind': 'olympic', 'title': col['title'], 'grade': col.get('grade', grade), 'year': col['year']}
        c.update(sourceName=col['sourceName'], sourceUrl=col['sourceUrl'], problems=probs)
        by.setdefault(fname, []).append(c)
        n += len(probs)
    for fname, cols in by.items():
        cols.sort(key=lambda c: (-c['year'], c['id']))
        write_json_atomic(CONTENT / 'sources' / f'{fname}.json', cols)
    log('build', {k: (len(v), sum(len(c['problems']) for c in v)) for k, v in by.items()}, 'total', n)


async def main():
    args = sys.argv[1:]
    if args == ['--build']:
        build(); return
    cols = [json.loads(f.read_text()) for f in sorted(RAW.glob('*.json'))]
    if args:
        cols = [c for c in cols if any(c['id'].startswith(a) for a in args)]
    g = Gemini(per_slot=2)
    sem = asyncio.Semaphore(10)
    last = [0]

    async def one(col):
        async with sem:
            await do_col(g, col)
        import time
        if time.time() - last[0] > 20:
            last[0] = time.time(); build()

    await asyncio.gather(*(one(c) for c in cols))
    build()
    log('stats', g.stats)
    if g.session:
        await g.session.close()


if __name__ == '__main__':
    asyncio.run(main())
