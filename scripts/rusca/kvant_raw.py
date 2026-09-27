"""Group Kvant M-problems by issue -> .cache/rusca/raw/kvant-<year>-<nn>.json"""
import json, re, html
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
RC = ROOT / '.cache/rusca'
RAW = RC / 'raw'
RAW.mkdir(parents=True, exist_ok=True)
CYR = 'абвгдежзик'


def clean(h):
    h = re.sub(r'<span class="tag--footnote.*?</ins></span>', '', h, flags=re.S)
    h = re.sub(r'<figure.*?</figure>', ' ', h, flags=re.S)
    h = h.replace('&zwj;', '').replace('<nowrap>', '').replace('</nowrap>', '')

    def ol(m):
        items = re.findall(r'<li>(.*?)</li>', m.group(0), re.S)
        num = 'decimal' in m.group(1) or 'arabic' in m.group(1)
        return '\n\n' + '\n\n'.join((f'{k+1})' if num else f'{CYR[k % 10]})') + ' ' + it.strip() for k, it in enumerate(items)) + '\n\n'
    h = re.sub(r'<ol([^>]*)>.*?</ol>', ol, h, flags=re.S)
    h = re.sub(r'<ul[^>]*>(.*?)</ul>', lambda m: '\n' + re.sub(r'<li>(.*?)</li>', r'\n- \1', m.group(1), flags=re.S) + '\n', h, flags=re.S)
    h = re.sub(r'</p>|<br\s*/?>', '\n\n', h)
    h = re.sub(r'<(i|em)>(.*?)</\1>', r'\2', h, flags=re.S)
    h = re.sub(r'<[^>]+>', '', h)
    h = html.unescape(h).replace('\xa0', ' ')
    h = re.sub(r'[ \t]*\n[ \t]*', '\n', h)
    h = re.sub(r'(?<!\n)\n(?!\n)', ' ', h)
    h = re.sub(r'\n{3,}', '\n\n', h)
    return h.strip()


probs = json.loads((RC / 'kvant/problems.json').read_text())
ocr = json.loads((RC / 'kvant/ocr.json').read_text()) if (RC / 'kvant/ocr.json').exists() else {}
by = {}
for p in probs:
    if not p['year'] or not p['issue']:
        continue
    by.setdefault((p['year'], p['issue']), []).append(p)
n = 0
for (y, iss), ps in sorted(by.items()):
    first = iss.split('-')[0].split('–')[0]
    cid = f'kvant-{y}-{int(first):02d}' if first.isdigit() else f'kvant-{y}-{re.sub(r"[^0-9a-z]+", "-", iss)}'
    ps.sort(key=lambda p: p['num'])
    col = {'id': cid, 'out': 'tapchi-kvant', 'kind': 'tapchi', 'lang': 'ru',
           'title': f'Tạp chí Kvant (Nga) số {iss}/{y} – Задачник «Кванта»',
           'grade': 9, 'year': y,
           'sourceName': f'Tạp chí Kvant (Nga) số {iss}/{y}',
           'sourceUrl': f'https://www.kvant.digital/issues/{y}/{iss.replace("/", "-")}/',
           'problems': [{'label': f'M{p["num"]}', 'src': clean(p['html']) if p['html'] else ocr[str(p['num'])]['src'],
                         'proposer': p['proposer'] if p['html'] else ocr[str(p['num'])].get('proposer', ''), 'images': p['figs'],
                         'url': f'https://www.kvant.digital/problems/m{p["num"]}/'} for p in ps
                        if p['html'] or ocr.get(str(p['num']), {}).get('src')]}
    if not col['problems']:
        continue
    (RAW / f'{cid}.json').write_text(json.dumps(col, ensure_ascii=False, indent=1))
    n += len(ps)
print('kvant issues', len(by), 'problems', n)
