/**
 * Prebuild for the web: content/**.json  →  .data/ (compact index + per-collection shards, KaTeX pre-rendered).
 * Run: node --no-warnings scripts/web/build-index.mts   (wired as prebuild/predev in package.json)
 * Env: SAMPLE=1 also includes "_" files. "_" files are otherwise used only when no real file yields data.
 */
import fs from 'node:fs';
import path from 'node:path';
import { md, snippetSrc } from '../../lib/md.ts';
import { TOPICS, KINDS } from '../../lib/topics.ts';

const ROOT = process.cwd();
const CONTENT = path.join(ROOT, 'content');
const OUT = path.join(ROOT, '.data');
const SAMPLE = process.env.SAMPLE === '1';
const t0 = Date.now();

const TOPIC_IDS = TOPICS.map((t) => t.id) as string[];
const isTopic = (s: unknown): s is string => typeof s === 'string' && TOPIC_IDS.includes(s);
const isKind = (s: unknown) => typeof s === 'string' && s in KINDS;
const str = (v: unknown) => (typeof v === 'string' ? v : '');
const arr = (v: unknown): any[] => (Array.isArray(v) ? v : []);
const lvl = (v: unknown) => Math.min(4, Math.max(1, Math.round(Number(v) || 1)));
const topicsOf = (v: unknown) => [...new Set(arr(v).filter(isTopic))];
export const fold = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[đĐ]/g, 'd').toLowerCase();
const plain = (s: string) =>
  s
    .replace(/\\(?:d?frac|sqrt|left|right|cdot|dfrac|widehat|overline|text|mathrm|begin|end|cases|le|ge|ne|in|pmod|quad)\b/g, ' ')
    .replace(/\\[a-zA-Z]+/g, ' ')
    .replace(/[{}$^_\\*#|&]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

let bad = 0;
function readJson(file: string): unknown {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (e) {
    bad++;
    console.warn(`[build-index] skip ${path.relative(ROOT, file)}: ${(e as Error).message}`);
    return undefined;
  }
}
const listJson = (dir: string) => {
  try {
    return fs.readdirSync(dir).filter((f) => f.endsWith('.json')).sort().map((f) => ({ name: f, file: path.join(dir, f) }));
  } catch {
    return [];
  }
};
function pick<T>(files: { name: string; file: string }[], parse: (d: unknown) => T[]) {
  const real = files.filter((f) => !f.name.startsWith('_')).flatMap((f) => parse(readJson(f.file)));
  if (real.length && !SAMPLE) return { items: real, sample: false };
  const samples = files.filter((f) => f.name.startsWith('_')).flatMap((f) => parse(readJson(f.file)));
  return { items: [...real, ...samples], sample: samples.length > 0 };
}

type P = { id: string; label: string; text: string; topics: string[]; level: number; hint?: string; solution?: string; answer?: string; source?: string };
type C = { id: string; kind: string; title: string; grade: number; year?: number; province?: string; sourceName: string; sourceUrl: string; problems: P[] };

const parseCollections = (d: unknown): C[] =>
  arr(d).flatMap((c) => {
    if (!c || !str(c.id) || !str(c.title)) return [];
    const grade = Number(c.grade);
    const year = Number(c.year);
    return [
      {
        id: c.id,
        kind: isKind(c.kind) ? c.kind : 'chuyende',
        title: c.title,
        grade: grade >= 6 && grade <= 10 ? grade : 9,
        year: Number.isFinite(year) && year > 1900 ? year : undefined,
        province: str(c.province) || undefined,
        sourceName: str(c.sourceName) || 'Không rõ nguồn',
        sourceUrl: /^https?:\/\//.test(str(c.sourceUrl)) ? c.sourceUrl : '',
        problems: arr(c.problems).flatMap((p) =>
          p && str(p.id) && str(p.text)
            ? [{ id: p.id, label: str(p.label) || 'Bài', text: p.text, topics: topicsOf(p.topics), level: lvl(p.level), hint: str(p.hint) || undefined, solution: str(p.solution) || undefined, answer: str(p.answer) || undefined, source: str(p.source) || str(p.proposer) || undefined }]
            : [],
        ),
      },
    ];
  });

// ---------- collections ----------
const src = pick(listJson(path.join(CONTENT, 'sources')), parseCollections);
const colMap = new Map<string, C>();
for (const c of src.items) {
  const prev = colMap.get(c.id);
  if (!prev || c.problems.length > prev.problems.length) colMap.set(c.id, c);
}
const cols = [...colMap.values()].filter((c) => c.problems.length);
cols.sort((a, b) => (b.year ?? 0) - (a.year ?? 0) || a.grade - b.grade || a.title.localeCompare(b.title, 'vi'));

// dedupe problems: same id → keep first; same normalized statement → dupOf canonical (preference: exam with year+province > tapchi > olympic > chuyende)
const pref = (c: C) => (c.kind === 'hsg' || c.kind === 'chuyen' ? (c.year && c.province ? 0 : 1) : c.kind === 'tapchi' ? 2 : c.kind === 'olympic' ? 3 : 4);
const seenId = new Set<string>();
for (const c of cols) c.problems = c.problems.filter((p) => !seenId.has(p.id) && (seenId.add(p.id), true));
const fp = (t: string) => fold(plain(t)).replace(/[^a-z0-9]+/g, '');
const canon = new Map<string, string>();
const dupOf = new Map<string, string>();
for (const c of [...cols].sort((a, b) => pref(a) - pref(b) || (b.year ?? 0) - (a.year ?? 0)))
  for (const p of c.problems) {
    const k = fp(p.text);
    if (k.length < 40) continue;
    const first = canon.get(k);
    if (first) dupOf.set(p.id, first);
    else canon.set(k, p.id);
  }

fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(path.join(OUT, 'col'), { recursive: true });
fs.mkdirSync(path.join(OUT, 'lesson'), { recursive: true });
const safe = (id: string) => id.replace(/[^a-zA-Z0-9_-]/g, (ch) => `~${ch.charCodeAt(0).toString(16)}`);
const write = (rel: string, data: unknown) => fs.writeFileSync(path.join(OUT, rel), JSON.stringify(data));

const probs: unknown[] = [];
const search: string[] = [];
const colRows: unknown[] = [];
const topicCount: Record<string, number> = Object.fromEntries(TOPIC_IDS.map((t) => [t, 0]));
const years = new Set<number>();
const provinces = new Set<string>();
let visible = 0;

cols.forEach((c, ci) => {
  const levels = [0, 0, 0, 0];
  for (const p of c.problems) levels[p.level - 1]++;
  if (c.year) years.add(c.year);
  if (c.province) provinces.add(c.province);
  colRows.push({ id: c.id, kind: c.kind, title: c.title, grade: c.grade, year: c.year, province: c.province, sourceName: c.sourceName, sourceUrl: c.sourceUrl, n: c.problems.length, levels, topics: [...new Set(c.problems.flatMap((p) => p.topics))] });
  const shard = c.problems.map((p) => {
    const d = dupOf.get(p.id);
    const mask = p.topics.reduce((m, t) => m | (1 << TOPIC_IDS.indexOf(t)), 0);
    probs.push([p.id, ci, p.label, p.level, mask, snippetSrc(p.text, 230), p.solution ? 1 : 0, d ?? 0]);
    search.push(fold(`${p.label} ${plain(p.text).slice(0, 400)} ${c.title} ${c.province ?? ''} ${c.year ?? ''} ${KINDS[c.kind as keyof typeof KINDS].name}`));
    if (!d) {
      visible++;
      for (const t of p.topics) topicCount[t]++;
    }
    return {
      id: p.id,
      label: p.label,
      level: p.level,
      topics: p.topics,
      desc: plain(p.text).slice(0, 160),
      html: md(p.text),
      hint: p.hint ? md(p.hint) : undefined,
      solution: p.solution ? md(p.solution) : undefined,
      answer: p.answer ? md(p.answer) : undefined,
      source: p.source,
      dupOf: d,
    };
  });
  write(`col/${safe(c.id)}.json`, shard);
});

// ---------- lessons ----------
const th = pick(listJson(path.join(CONTENT, 'theory')), (d) =>
  arr(d).flatMap((l) => (l && str(l.id) && str(l.title) && isTopic(l.topic) ? [{ id: str(l.id), topic: str(l.topic), level: lvl(l.level), title: str(l.title), summary: str(l.summary), body: str(l.body), examples: arr(l.examples).filter((e) => e && str(e.text)) }] : [])),
);
const lessonMap = new Map<string, (typeof th.items)[number]>();
for (const l of th.items) if (!lessonMap.has(l.id)) lessonMap.set(l.id, l);
const lessons = [...lessonMap.values()].sort((a, b) => a.level - b.level || a.title.localeCompare(b.title, 'vi'));
// learning path: same topic, belts from lesson level upward, newest first, no duplicates
const byTopicLevel = new Map<string, string[]>();
for (const c of cols)
  for (const p of c.problems)
    if (!dupOf.has(p.id))
      for (const t of p.topics) {
        const k = `${t}:${p.level}`;
        const list = byTopicLevel.get(k) ?? byTopicLevel.set(k, []).get(k)!;
        list.push(p.id);
      }
const lessonRows = lessons.map((l, i) => {
  const path_: string[][] = [];
  for (let lv = l.level; lv <= Math.min(4, l.level + 2); lv++) {
    const pool = byTopicLevel.get(`${l.topic}:${lv}`) ?? [];
    const start = pool.length ? (i * 7) % pool.length : 0;
    path_.push(Array.from({ length: Math.min(4, pool.length) }, (_, j) => pool[(start + j) % pool.length]));
  }
  write(`lesson/${safe(l.id)}.json`, { body: md(l.body), examples: l.examples.map((e) => ({ text: md(str(e.text)), solution: str(e.solution) ? md(str(e.solution)) : undefined })) });
  return { id: l.id, topic: l.topic, level: l.level, title: l.title, summary: l.summary, nEx: l.examples.length, path: path_ };
});

// ---------- books ----------
const parseBooks = (d: unknown) =>
  arr(d).flatMap((b) =>
    b && str(b.id) && str(b.title) && /^https?:\/\//.test(str(b.url))
      ? [{ id: b.id, title: b.title, author: str(b.author) || undefined, publisher: str(b.publisher) || undefined, grades: arr(b.grades).map(Number).filter((g) => g >= 6 && g <= 10), topics: topicsOf(b.topics), desc: str(b.desc), url: b.url, source: str(b.source) }]
      : [],
  );
const booksFile = path.join(CONTENT, 'books.json');
let books = SAMPLE || !fs.existsSync(booksFile) ? [] : parseBooks(readJson(booksFile));
let bookSample = false;
if (!books.length) {
  const f = path.join(CONTENT, 'books.json');
  const s = fs.existsSync(path.join(CONTENT, '_books.sample.json')) ? parseBooks(readJson(path.join(CONTENT, '_books.sample.json'))) : [];
  books = [...(fs.existsSync(f) ? parseBooks(readJson(f)) : []), ...s];
  bookSample = s.length > 0;
}
books = [...new Map(books.map((b) => [b.id, b])).values()];

const sample = { sources: src.sample, theory: th.sample, books: bookSample };
const meta = {
  builtAt: new Date().toISOString(),
  sample,
  stats: { collections: cols.length, problems: visible, lessons: lessons.length, books: books.length, dups: dupOf.size },
  topicCount,
  facets: { years: [...years].sort((a, b) => b - a), provinces: [...provinces].sort((a, b) => a.localeCompare(b, 'vi')) },
};
write('meta.json', meta);
write('index.json', { cols: colRows, probs, lessons: lessonRows, books });
write('search.json', search);
console.log(`[build-index] ${cols.length} collections, ${probs.length} problems (${dupOf.size} dup), ${lessons.length} lessons, ${books.length} books${Object.values(sample).some(Boolean) ? ' (with sample data)' : ''}${bad ? `, ${bad} unreadable files` : ''} → .data in ${Date.now() - t0} ms`);
