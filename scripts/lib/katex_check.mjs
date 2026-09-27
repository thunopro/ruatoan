// KaTeX/markdown checker mirroring lib/md.ts (block split, "- " lists, | tables |, math delimiters).
// Usage:
//   node katex_check.mjs < strings.json          -> JSON array of error messages (null when ok), same order
//   node katex_check.mjs --file content/toan.json -> prints report of bad strings (id, field, error), exit 1 if any
import katex from '../../node_modules/katex/dist/katex.mjs';
import fs from 'node:fs';
console.warn = () => {};

const MATH = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\$([^$\n]+?)\$|\\\(([\s\S]+?)\\\)/g;
// LaTeX commands that should never appear in plain text (outside math)
const BARE = /\\(?:[a-zA-Z]+)(?![a-zA-Z])/;

function checkInline(s) {
  let rest = '';
  let last = 0;
  const re = new RegExp(MATH.source, 'g');
  for (let m; (m = re.exec(s)); ) {
    rest += s.slice(last, m.index) + ' ';
    const t = m[1] ?? m[2] ?? m[3] ?? m[4];
    const display = m[1] !== undefined || m[2] !== undefined;
    try {
      katex.renderToString(t, { displayMode: display, throwOnError: true, strict: 'ignore', output: 'html' });
    } catch (e) {
      return String(e.message || e).replace(/\s+/g, ' ').slice(0, 160);
    }
    if (!t.trim()) return 'empty math';
    last = re.lastIndex;
  }
  rest += s.slice(last);
  if (rest.includes('$')) return 'unbalanced $';
  const b = rest.match(BARE);
  if (b) return `latex outside math: ${b[0]}`;
  if (/\^\{|_\{/.test(rest)) return 'latex outside math: ^{ / _{';
  return null;
}

export function check(src) {
  src = String(src ?? '');
  if (!src.trim()) return 'empty';
  const blocks = src.replace(/\r/g, '').trim().split(/\n\s*\n/);
  for (const b of blocks) {
    const lines = b.split('\n');
    let err = null;
    if (lines.every((l) => /^\s*[-•]\s+/.test(l))) {
      for (const l of lines) if ((err = checkInline(l.replace(/^\s*[-•]\s+/, '')))) break;
    } else if (lines.length > 1 && lines.every((l) => /^\s*\|.*\|\s*$/.test(l))) {
      const rows = lines.filter((l) => !/^\s*\|[\s:|-]+\|\s*$/.test(l)).map((l) => l.trim().slice(1, -1).split('|'));
      outer: for (const r of rows) for (const c of r) if ((err = checkInline(c.trim()))) { err = 'table cell: ' + err; break outer; }
    } else {
      const h = b.match(/^(#{1,3})\s+(.*)$/);
      err = checkInline(h && lines.length === 1 ? h[2] : b);
    }
    if (err) return err;
  }
  return null;
}

const args = process.argv.slice(2);
if (args[0] === '--file') {
  const exams = JSON.parse(fs.readFileSync(args[1], 'utf8'));
  let n = 0, bad = 0;
  const counts = {};
  for (const ex of exams)
    for (const p of ex.problems)
      for (const f of ['text', 'answer']) {
        if (p[f] === undefined) continue;
        n++;
        const e = check(p[f]);
        if (e) {
          bad++;
          const k = e.replace(/ at position.*| in .*|: .*/, '');
          counts[k] = (counts[k] || 0) + 1;
          if (!args.includes('--quiet')) console.log(JSON.stringify({ id: p.id, f, e }));
        }
      }
  console.log(`checked ${n} strings, bad ${bad}`, JSON.stringify(counts));
  process.exit(bad ? 1 : 0);
} else if (import.meta.url === `file://${process.argv[1]}`) {
  const items = JSON.parse(fs.readFileSync(0, 'utf8'));
  process.stdout.write(JSON.stringify(items.map(check)));
}
