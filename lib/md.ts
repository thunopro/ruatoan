import katex from 'katex';

const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
const tex = (s: string, displayMode: boolean) => {
  try {
    return katex.renderToString(s, { displayMode, throwOnError: false, strict: 'ignore', output: 'html' });
  } catch {
    return esc(s);
  }
};

function inline(s: string) {
  const out: string[] = [];
  const re = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\$([^$\n]+?)\$|\\\(([\s\S]+?)\\\)/g;
  let last = 0;
  for (let m; (m = re.exec(s)); ) {
    out.push(fmt(s.slice(last, m.index)));
    out.push(m[1] !== undefined || m[2] !== undefined ? `<div class="mathd">${tex(m[1] ?? m[2], true)}</div>` : tex(m[3] ?? m[4], false));
    last = re.lastIndex;
  }
  out.push(fmt(s.slice(last)));
  return out.join('');
}

const fmt = (s: string) =>
  esc(s)
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<i>$2</i>')
    .replace(/\n/g, '<br>');

const isLi = (l: string) => /^\s*[-•]\s+/.test(l);

function block(b: string): string {
  const lines = b.split('\n');
  if (lines.every(isLi)) return `<ul>${lines.map((l) => `<li>${inline(l.replace(/^\s*[-•]\s+/, ''))}</li>`).join('')}</ul>`;
  if (lines.length > 1 && lines.every((l) => /^\s*\|.*\|\s*$/.test(l))) {
    const rows = lines.filter((l) => !/^\s*\|[\s:|-]+\|\s*$/.test(l)).map((l) => l.trim().slice(1, -1).split('|'));
    return `<div class="tbl"><table>${rows.map((r, i) => `<tr>${r.map((c) => (i ? `<td>${inline(c.trim())}</td>` : `<th>${inline(c.trim())}</th>`)).join('')}</tr>`).join('')}</table></div>`;
  }
  const h = b.match(/^(#{1,3})\s+(.*)$/);
  if (h && lines.length === 1) return `<h${h[1].length + 2}>${inline(h[2])}</h${h[1].length + 2}>`;
  // "Intro:\n- a\n- b" → paragraph + list (only outside display math)
  if (!b.includes('$$') && lines.some(isLi) && !lines.every(isLi)) {
    const runs: string[][] = [];
    for (const l of lines) {
      const last = runs[runs.length - 1];
      if (last && isLi(last[0]) === isLi(l)) last.push(l);
      else runs.push([l]);
    }
    return runs.map((r) => block(r.join('\n'))).join('');
  }
  return `<p>${inline(b)}</p>`;
}

/** Tiny markdown: paragraphs, "## " headings, "- " lists, **bold**, *italic*, $inline$ and $$display$$ math, | tables |. */
export function md(src: string) {
  if (!src) return '';
  return src
    .replace(/\r/g, '')
    .replace(/^(#{1,3}\s+.*)$/gm, '\n$1\n')
    .trim()
    .split(/\n\s*\n/)
    .map((b) => b.replace(/^\n+|\n+$/g, ''))
    .filter(Boolean)
    .map(block)
    .join('');
}

/** Plain-ish snippet of markdown+math that never cuts inside $…$ / $$…$$. */
export function snippetSrc(src: string, max = 220): string {
  const s = src.replace(/\r/g, '').replace(/\n\s*\n/g, '\n').trim();
  const re = /\$\$[\s\S]+?\$\$|\$[^$\n]+?\$/g;
  let out = '';
  let last = 0;
  let len = 0;
  const pushText = (t: string) => {
    if (len + t.length <= max) {
      out += t;
      len += t.length;
      return true;
    }
    const room = max - len;
    let cut = t.slice(0, room);
    const sp = cut.lastIndexOf(' ');
    if (sp > room * 0.5) cut = cut.slice(0, sp);
    out += cut;
    len = max;
    return false;
  };
  for (let m; (m = re.exec(s)); ) {
    if (!pushText(s.slice(last, m.index))) return out.trimEnd() + ' …';
    const math = m[0].startsWith('$$') ? `$${m[0].slice(2, -2).replace(/\s*\n\s*/g, ' ')}$` : m[0];
    const w = Math.min(60, Math.ceil(math.length / 3));
    if (len + w > max && len > max * 0.4) return out.trimEnd() + ' …';
    out += math;
    len += w;
    last = re.lastIndex;
  }
  if (!pushText(s.slice(last))) return out.trimEnd() + ' …';
  return out;
}


export const snippet = (src: string, max = 220) => ({ html: md(snippetSrc(src, max)) });
