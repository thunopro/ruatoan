"""«Квант» для младших школьников – Задачи (statements only) -> .cache/rusca/raw/kvant-<year>-<nn>-tre.json
Text articles: <ol><li> items parsed from the statement block (answers block is cut off).
Scan-only articles: page scans transcribed with Gemini vision (statements only)."""
import asyncio, json, re, html, sys
from pathlib import Path
import aiohttp
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import log, ROOT, write_json_atomic
from gemini import Gemini, FLASH, NoCapacity, file_part, sha
from kvant_raw_clean import clean

RC = ROOT / '.cache/rusca'
K = RC / 'kvant'
RAW = RC / 'raw'
PG = K / 'pages'
MODELS = ['gemini-3.5-flash-lite'] + FLASH + ['gemini-3.1-flash-lite', 'gemini-flash-lite-latest', 'gemini-3.1-flash-lite-preview', 'gemini-2.5-flash-lite', 'gemma-4-31b-it', 'gemma-4-26b-a4b-it']
SCHEMA = {'type': 'object', 'properties': {'problems': {'type': 'array', 'items': {'type': 'object', 'properties': {
    'number': {'type': 'integer'}, 'statement': {'type': 'string'}, 'proposer': {'type': 'string'}},
    'required': ['number', 'statement', 'proposer']}}}, 'required': ['problems']}


def art_file(a):
    return K / 'issues' / ('art_' + re.sub(r'\W+', '_', a['url'][30:]) + '.html')


def top_items(blk):
    # split the first-level <ol> into its top-level <li> items (nested lists kept inside)
    items, depth, start = [], 0, None
    for m in re.finditer(r'<(/?)(ol|ul|li)\b[^>]*>', blk):
        close, tag = m.group(1), m.group(2)
        if tag in ('ol', 'ul'):
            depth += -1 if close else 1
        elif depth == 1:
            if not close:
                start = m.end()
            elif start is not None:
                items.append(blk[start:m.start()]); start = None
    return items


def parse_text(s):
    i = s.find('<span class="no-copy">Текст статьи</span>')
    if i < 0:
        return None
    j = s.find('Ответы, указания, решения', i)
    end = s.find('<div class="media--screen no-copy block--buttons', i)
    blk = s[i:min(x for x in (j, end) if x > 0)]
    items = top_items(blk)
    out = []
    for it in items:
        figs = ['https:' + u if u.startswith('//') else u for u in re.findall(r'<img src="([^"]+)"', it)]
        prop = ''
        pm = re.search(r'<p class="meta--inscription">(.*?)</p>', it, re.S)
        if pm:
            prop = html.unescape(re.sub(r'<[^>]+>', '', pm.group(1))).replace('\xa0', ' ').strip()
            it = it.replace(pm.group(0), '')
        t = clean(it)
        if len(t) > 15:
            out.append({'src': t, 'proposer': prop, 'images': figs})
    return out


async def main():
    arts = json.loads((K / 'junior.json').read_text())
    ocr_p = K / 'junior_ocr.json'
    ocr = json.loads(ocr_p.read_text()) if ocr_p.exists() else {}
    g = Gemini(per_slot=2)
    sem = asyncio.Semaphore(6)
    lock = asyncio.Lock()
    stop = [False]
    async with aiohttp.ClientSession(headers={'User-Agent': 'Mozilla/5.0'}, timeout=aiohttp.ClientTimeout(total=90)) as sess:
        async def one(a):
            s = art_file(a).read_text() if art_file(a).exists() else ''
            probs = parse_text(s) if 'Текст статьи' in s else None
            key = a['url']
            if probs is None:
                if key not in ocr and not stop[0] and a['pages']:
                    async with sem:
                        files = []
                        for u in a['pages'][:2]:
                            f = PG / (re.sub(r'\W+', '_', u[30:]))
                            if not f.exists():
                                try:
                                    async with sess.get(u) as r:
                                        b = await r.read()
                                        if r.status == 200:
                                            f.write_bytes(b)
                                except Exception:
                                    pass
                            if f.exists():
                                files.append(f)
                        if not files:
                            return
                        prompt = ('The attached images are scanned pages of the Russian magazine «Квант», section «„Квант“ для младших школьников» — «Задачи». '
                                  'Transcribe EXACTLY (in Russian) the numbered problem STATEMENTS of this «Задачи» section only. '
                                  'Do NOT transcribe answers, hints or solutions, nor other articles on the page. Write math in LaTeX $...$. '
                                  'If a problem refers to a picture, add a precise description of the picture in Russian in square brackets. '
                                  'proposer = author name printed with the problem, empty if none. number = problem number in the section. Never invent text.')
                        try:
                            r = await g.generate([file_part(f, 'image/jpeg') for f in files] + [{'text': prompt}], models=MODELS, schema=SCHEMA,
                                                 cache_key=f'rc-kvjr/{sha(key)}', temperature=0.1, max_tries=10)
                        except NoCapacity:
                            stop[0] = True; return
                        except Exception as e:
                            log('fail', key, str(e)[:100]); return
                        async with lock:
                            ocr[key] = [{'src': (p.get('statement') or '').strip(), 'proposer': (p.get('proposer') or '').strip(), 'images': []}
                                        for p in sorted(r['result'].get('problems', []), key=lambda p: p.get('number', 0)) if len(p.get('statement') or '') > 15]
                            write_json_atomic(ocr_p, ocr)
                        log('ocr', key, len(ocr[key]), r['model'])
                probs = ocr.get(key)
            if not probs:
                return
            y, iss = a['year'], a['issue']
            first = re.split(r'[/\-–]', iss)[0]
            cid = f'kvant-{y}-{int(first):02d}-tre'
            col = {'id': cid, 'out': 'tapchi-kvant', 'kind': 'tapchi', 'lang': 'ru', 'year': y, 'grade': 7,
                   'title': f'Tạp chí Kvant (Nga) số {iss}/{y} – «Kvant cho học sinh nhỏ tuổi»',
                   'sourceName': f'Tạp chí Kvant (Nga) số {iss}/{y}, mục «Kvant cho học sinh nhỏ tuổi»',
                   'sourceUrl': a['url'],
                   'problems': [dict(p, label=f'Bài {k + 1}') for k, p in enumerate(probs)]}
            write_json_atomic(RAW / f'{cid}.json', col)
        await asyncio.gather(*(one(a) for a in arts))
    log('stats', g.stats, 'stopped' if stop[0] else '')
    if g.session:
        await g.session.close()

asyncio.run(main())
