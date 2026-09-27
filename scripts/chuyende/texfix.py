"""Deterministic LaTeX/JSON-escape repairs for model output (adapted from ../toanthcs/scripts/ingest/toan.py)."""
import re

CTRL = {'\x0c': '\\f', '\t': '\\t', '\x08': '\\b', '\r': '\\r', '\x0b': '\\v', '\x07': '\\a'}


def repair(s):
    s = str(s or '')
    for a, b in CTRL.items():
        s = s.replace(a, b)
    return clean_tex(s.strip())


# --- deterministic LaTeX repairs for typical model/JSON-escape artefacts -------------------------------------
_ARROW = r'\Leftrightarrow'
_ENVS = r'(?:cases|array|aligned|matrix|bmatrix|pmatrix|align\*?|gathered)'
_TEX_RULES = [
    # "\u21d4" written literally
    (r'\\u21d4', r'\\Leftrightarrow'), (r'\\u21d2', r'\\Rightarrow'), (r'\\u00c1', r'\\sim'),
    # \textbackslash{} escaped commands: \text{\textbackslash{}sqrt}{49} -> \sqrt{49}
    (r'\\text\{\\textbackslash\{\}([a-zA-Z]+)\}', r'\\\1'), (r'\\textbackslash\{\}([a-zA-Z]+)', r'\\\1'),
    (r'\\backslash ?(sqrt|Rightarrow|Leftrightarrow|frac|dfrac|cdot|widehat)', r'\\\1'),
    # double-escaped commands inside math: \\bar{7} -> \bar{7}, \\text{dm} -> \text{dm}
    (r'\\\\(bar|text|sqrt|frac|dfrac|cdot|widehat|pi|Rightarrow|Leftrightarrow)(?![a-zA-Z])', r'\\\1'),
    # sqrt spelled as \root{..}, \root(..), \bar{..}
    (r'\\root\(([^()]*)\)', r'\\sqrt{\1}'), (r'\\root(?![a-zA-Z])', r'\\sqrt'),
    (r'\\bar\{\\sqrt\{([^{}]*)\}\}', r'\\sqrt{\1}'), (r'4\\bar\{r\}\^2', r'4\\pi r^2'), (r'\\bar\{', r'\\sqrt{'),
    (r'\\therefore(?![a-zA-Z])', r'\\Rightarrow'),
    (r'\\brak\{', r'\\left('),
    # arcs
    (r'\\(?:overparen|wideparen)(?![a-zA-Z])', r'\\overset{\\frown}'),
    # tab/formfeed artefacts: \t<cmd> where <cmd> is a real command
    (r'\\t(Rightarrow|Leftrightarrow|leq|geq|approx|bot|perp|iff|sim)(?![a-zA-Z])', r'\\\1'),
    (r'\\t(?:hex|thuyet|ahtarrow|a)(?![a-zA-Z])', _ARROW.replace('\\', '\\\\')),
    (r'\\tcos(?![a-zA-Z])', r'\\sim'),
    (r'\\bfit\{(\\text\{[^{}]*\})\}', r'\1'),
    (r'\\thinsp(?![a-zA-Z])', r'\\,'), (r'\\thickapprox(?![a-zA-Z])', r'\\approx'),
    (r'\\begin\{widehat\}\{\}', r'\\begin{array}{l}'), (r'\\end\{widehat\}', r'\\end{array}'),
    (r'\\bgroup(.*?)\\bgroup', r'\\{\1\\}'),
    # bare 3-letter angle names: \ABC -> \widehat{ABC}
    (r'\\([A-Z]{3})(?![a-zA-Z])', r'\\widehat{\1}'),
    # escaped newline written literally ("\\n") before text/markdown (not \neq, \notin...)
    (r'\\n(?=[A-ZĐÀ-Ỹ$\-*(0-9]|\s)', '\n'),
    # real newline eaten the "\n" of \neq / \notin / \ngeq ... (JSON "\neq" decoded as newline+"eq")
    (r'(?<=[\s$({])\n(eq|otin|ot|e|geq|leq|mid|parallel|exists)(?![a-zA-Z])', r'\\n\1'),
    (r'\n(cdot|Leftrightarrow|Rightarrow|left|right|frac|dfrac|sqrt|quad|le|ge|times)(?![a-zA-Z])', r' \\\1'),
    (r'\nes(?![a-zA-Z])', r'\\end{cases}'),
]
_TEX_RULES = [(re.compile(a), b) for a, b in _TEX_RULES]


def _fix_env_rows(m):
    body = m.group(0)
    # single "\ " used as row separator inside cases/array -> "\\ "
    return re.sub(r'(?<![\\])\\ (?=\s*[-+(]?[a-zA-Z0-9\\])', r'\\\\ ', body)


def _fix_inline_newlines(s):
    # newline inside an inline $...$ (lib/md.ts does not match inline math across lines)
    out, i = [], 0
    for m in re.finditer(r'\$\$[\s\S]+?\$\$|\$([^$]+?)\$', s):
        seg = m.group(0)
        if m.group(1) is not None and '\n' in seg and not re.search(r'\n\s*\n', seg) and len(seg) < 400 \
                and re.search(r'\\\\|\\end|\\cdot|\\Leftrightarrow|\\Rightarrow|=|\\right', seg):
            seg = re.sub(r'\s*\n\s*', ' ', seg)
        out.append(s[i:m.start()] + seg)
        i = m.end()
    return ''.join(out) + s[i:]


def _close_dollar(s):
    # odd number of $: close a trailing unterminated inline formula before final punctuation
    n = len(re.findall(r'(?<!\\)\$', s))
    if n % 2 == 0:
        return s
    last = max(i for i in range(len(s)) if s[i] == '$' and (i == 0 or s[i - 1] != '\\'))
    tail = s[last + 1:]
    if '\n' in tail or not tail.strip():
        return s
    m = re.match(r'^(.*?)([.;,]?\)?\s*)$', tail, re.S)
    return s[:last + 1] + m.group(1) + '$' + m.group(2)


def _unwrap_cmd(s, cmd, need_inner_cmd):
    """\\cmd{body} -> body (balanced braces); for \\text only when body starts with a math command."""
    out, i, key = [], 0, '\\' + cmd + '{'
    while True:
        j = s.find(key, i)
        if j < 0:
            return ''.join(out) + s[i:]
        k, depth = j + len(key), 1
        while k < len(s) and depth:
            if s[k - 1] != '\\':
                depth += {'{': 1, '}': -1}.get(s[k], 0)
            k += 1
        body = s[j + len(key):k - 1]
        if depth == 0 and (not need_inner_cmd or re.match(r'\\(?!text)[a-zA-Z]', body)):
            out.append(s[i:j] + body)
            i = k
        else:
            out.append(s[i:j + len(key)])
            i = j + len(key)


def clean_tex(s):
    if not s:
        return s
    s = _unwrap_cmd(_unwrap_cmd(s, 'bfit', False), 'text', True)
    for rx, rep in _TEX_RULES:
        s = rx.sub(rep, s)
    s = re.sub(r'\\begin\{' + _ENVS + r'\}[\s\S]*?\\end\{' + _ENVS + r'\}', _fix_env_rows, s)
    s = _fix_inline_newlines(s)
    s = _close_dollar(s)
    return s
