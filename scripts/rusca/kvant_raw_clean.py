"""HTML -> text cleaner for kvant.digital statement blocks."""
import re, html

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


