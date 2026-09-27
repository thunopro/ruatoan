"""Fetch JBMO + JBMO Shortlist post pages from pregatirematematicaolimpiadejuniori.wordpress.com
and list/download attachments of the post body. Output: .cache/olympic/jbmo/index.json"""
import json, re, html, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '.cache/olympic/jbmo'
OUT.mkdir(parents=True, exist_ok=True)
BASE = 'https://pregatirematematicaolimpiadejuniori.wordpress.com'

def get(url, dest=None):
    args = ['curl', '-sL', '--max-time', '120', '-A', 'Mozilla/5.0']
    if dest:
        subprocess.run(args + ['-o', str(dest), url], check=False)
        return None
    return subprocess.run(args + [url], capture_output=True, text=True).stdout

menu = open(sys.argv[1]).read()
items = re.findall(r'<a href="(https://pregatirematematicaolimpiadejuniori\.wordpress\.com/[^"]+)">((?:JBMO|SHL|ShL)\s*\d{4})</a>', menu, re.I)
items.append((BASE + '/2016/07/12/jbmo2012/', 'JBMO2012'))
index = []
for url, name in items:
    kind = 'jbmo' if name.upper().startswith('JBMO') else 'shl'
    year = int(re.search(r'\d{4}', name).group())
    key = f'{kind}{year}'
    pf = OUT / f'{key}.html'
    if not pf.exists():
        pf.write_text(get(url))
    s = pf.read_text()
    i = s.find('pd_rating_holder')
    if i < 0:
        i = s.find('class="post-content')
    j = s.find('sharedaddy', i)
    body = s[i:j]
    links = []
    for h in re.findall(r'(?:href|data-orig-file)="([^"]+)"', body):
        h = html.unescape(h).split('?')[0]
        if re.search(r'\.(pdf|docx?|jpe?g|png|gif)$', h, re.I) and 'wp-content/uploads' in h and h not in links:
            links.append(h)
    text = html.unescape(re.sub(r'<[^>]+>', ' ', body))
    text = re.sub(r'\s+', ' ', text)[:1500]
    index.append({'key': key, 'kind': kind, 'year': year, 'url': url, 'links': links, 'text': text})
    print(key, url, len(links))
    for l in links:
        if re.search(r'\.(pdf|docx?)$', l, re.I):
            d = OUT / 'files' / key / l.rsplit('/', 1)[1]
            d.parent.mkdir(parents=True, exist_ok=True)
            if not d.exists():
                get(l, d)
(OUT / 'index.json').write_text(json.dumps(index, ensure_ascii=False, indent=1))
