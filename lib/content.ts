import fs from 'node:fs';
import path from 'node:path';
import { isKind, toTopic, type Kind, type TopicId } from './topics';

export type Problem = { id: string; label: string; text: string; topics: TopicId[] };
export type Collection = {
  id: string;
  kind: Kind;
  title: string;
  grade: number;
  year?: number;
  province?: string;
  sourceName: string;
  sourceUrl: string;
  problems: Problem[];
};
export type Lesson = { id: string; topic: TopicId; title: string; summary: string; body: string; examples?: { text: string }[] };
export type Stage = 1 | 2 | 3;
export type Lang = 'vi' | 'en' | 'ru';
export type Book = { id: string; title: string; author?: string; publisher?: string; grades: number[]; topics: TopicId[]; desc: string; url: string; source: string; stage?: Stage; free?: boolean; lang?: Lang; kind: 'book' | 'magazine' };
export type Doc = { id: string; topic: TopicId; title: string; author?: string; grades: number[]; pages?: number; desc: string; url: string; pdf?: string; source: string; stage?: Stage; lang?: Lang };

type Entry = { problem: Problem; col: Collection; index: number; norm: string };
type Store = {
  collections: Collection[];
  colById: Map<string, Collection>;
  entries: Entry[]; // corpus order: collections by year desc, problems in paper order
  byId: Map<string, Entry>;
  byTopic: Map<TopicId, Entry[]>;
  lessons: Lesson[];
  lessonById: Map<string, Lesson>;
  books: Book[];
  docs: Doc[];
  sample: { sources: boolean; theory: boolean; books: boolean };
};

const ROOT = path.join(process.cwd(), 'content');
const SAMPLE = process.env.SAMPLE === '1';

/** Lowercase, no diacritics, đ→d — for accent-insensitive search. */
export const fold = (s: string) =>
  s.normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[\u0111\u0110]/g, 'd').toLowerCase();

// ---------- file reading with per-file mtime cache (crawlers write while we run) ----------
const fileCache = new Map<string, { mtime: number; data: unknown }>();
function readJson(file: string): unknown {
  let st: fs.Stats;
  try {
    st = fs.statSync(file);
  } catch {
    fileCache.delete(file);
    return undefined;
  }
  const hit = fileCache.get(file);
  if (hit && hit.mtime === st.mtimeMs) return hit.data;
  try {
    const data = JSON.parse(fs.readFileSync(file, 'utf8'));
    fileCache.set(file, { mtime: st.mtimeMs, data });
    return data;
  } catch (e) {
    console.warn(`[content] cannot parse ${file}: ${(e as Error).message}`);
    return hit?.data; // keep last good version
  }
}
const listJson = (dir: string) => {
  try {
    return fs.readdirSync(dir).filter((f) => f.endsWith('.json')).sort().map((f) => ({ name: f, file: path.join(dir, f) }));
  } catch {
    return [];
  }
};
/** Real files first; "_" files only when SAMPLE=1 or when no real file yields data. */
function pick<T>(files: { name: string; file: string }[], parse: (d: unknown) => T[]): { items: T[]; sample: boolean } {
  const real = files.filter((f) => !f.name.startsWith('_')).flatMap((f) => parse(readJson(f.file)));
  if (real.length && !SAMPLE) return { items: real, sample: false };
  const samples = files.filter((f) => f.name.startsWith('_')).flatMap((f) => parse(readJson(f.file)));
  return { items: [...real, ...samples], sample: samples.length > 0 };
}

const str = (v: unknown) => (typeof v === 'string' ? v : '');
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const topics = (v: unknown) => [...new Set(arr(v).map(toTopic).filter(Boolean))] as TopicId[];
const grades = (v: unknown) => arr(v).map(Number).filter((g) => g >= 6 && g <= 10);
const stage = (v: unknown) => ([1, 2, 3].includes(Number(v)) ? (Number(v) as Stage) : undefined);
const lang = (v: unknown) => (v === 'vi' || v === 'en' || v === 'ru' ? v : undefined);
const url = (v: unknown) => (/^https?:\/\//.test(str(v)) ? str(v) : '');

function parseCollections(d: unknown): Collection[] {
  return arr(d).flatMap((c: any) => {
    if (!c || !str(c.id) || !str(c.title)) return [];
    const problems = arr(c.problems).flatMap((p: any) =>
      p && str(p.id) && str(p.text)
        ? [{ id: p.id, label: str(p.label) || 'Bài', text: p.text, topics: topics(p.topics) }]
        : [],
    );
    const grade = Number(c.grade);
    return [
      {
        id: c.id,
        kind: isKind(c.kind) ? c.kind : 'chuyende',
        title: c.title,
        grade: grade >= 6 && grade <= 10 ? grade : 9,
        year: Number.isFinite(Number(c.year)) && Number(c.year) > 1900 ? Number(c.year) : undefined,
        province: str(c.province) || undefined,
        sourceName: str(c.sourceName) || 'Không rõ nguồn',
        sourceUrl: str(c.sourceUrl),
        problems,
      },
    ];
  });
}
const parseLessons = (d: unknown): Lesson[] =>
  arr(d).flatMap((l: any) =>
    l && str(l.id) && str(l.title) && toTopic(l.topic)
      ? [{ id: l.id, topic: toTopic(l.topic)!, title: l.title, summary: str(l.summary), body: str(l.body), examples: arr(l.examples).filter((e: any) => e && str(e.text)).map((e: any) => ({ text: e.text })) }]
      : [],
  );
const parseBooks = (d: unknown): Book[] =>
  arr(d).flatMap((b: any) =>
    b && str(b.id) && str(b.title) && url(b.url)
      ? [{ id: b.id, title: b.title, author: str(b.author) || undefined, publisher: str(b.publisher) || undefined, grades: grades(b.grades), topics: topics(b.topics), desc: str(b.desc), url: b.url, source: str(b.source), stage: stage(b.stage), free: typeof b.free === 'boolean' ? b.free : undefined, lang: lang(b.lang), kind: b.kind === 'magazine' ? 'magazine' : 'book' }]
      : [],
  );
const parseDocs = (d: unknown): Doc[] =>
  arr(d).flatMap((x: any) =>
    x && str(x.id) && str(x.title) && toTopic(x.topic) && url(x.url)
      ? [{ id: x.id, topic: toTopic(x.topic)!, title: x.title, author: str(x.author) || undefined, grades: grades(x.grades), pages: Number(x.pages) > 0 ? Number(x.pages) : undefined, desc: str(x.desc), url: x.url, pdf: url(x.pdf) || undefined, source: str(x.source), stage: stage(x.stage), lang: lang(x.lang) }]
      : [],
  );

// ---------- store ----------
let store: Store | null = null;
let signature = '';
let checkedAt = 0;

function currentSignature() {
  const parts: string[] = [];
  for (const dir of ['sources', 'theory']) for (const f of listJson(path.join(ROOT, dir))) parts.push(`${f.file}:${mtime(f.file)}`);
  for (const f of ['books.json', '_books.sample.json', 'docs.json']) parts.push(`${f}:${mtime(path.join(ROOT, f))}`);
  return parts.join('|');
}
function mtime(file: string) {
  try {
    return fs.statSync(file).mtimeMs;
  } catch {
    return 0;
  }
}

function build(): Store {
  const src = pick(listJson(path.join(ROOT, 'sources')), parseCollections);
  // dedupe collections (keep the richer one), then problems (first wins)
  const colMap = new Map<string, Collection>();
  for (const c of src.items) {
    const prev = colMap.get(c.id);
    if (!prev || c.problems.length > prev.problems.length) colMap.set(c.id, c);
  }
  const collections = [...colMap.values()].sort(
    (a, b) => (b.year ?? 0) - (a.year ?? 0) || a.grade - b.grade || a.title.localeCompare(b.title, 'vi'),
  );
  const byId = new Map<string, Entry>();
  const entries: Entry[] = [];
  const byTopic = new Map<TopicId, Entry[]>();
  for (const col of collections) {
    col.problems = col.problems.filter((p) => !byId.has(p.id) && (byId.set(p.id, null as never), true));
    col.problems.forEach((problem, index) => {
      const e: Entry = { problem, col, index, norm: fold(`${problem.label} ${problem.text} ${col.title} ${col.province ?? ''} ${col.sourceName}`) };
      byId.set(problem.id, e);
      entries.push(e);
      for (const t of problem.topics) (byTopic.get(t) ?? byTopic.set(t, []).get(t)!).push(e);
    });
  }
  const colById = new Map(collections.map((c) => [c.id, c]));

  const th = pick(listJson(path.join(ROOT, 'theory')), parseLessons);
  const lessonById = new Map<string, Lesson>();
  for (const l of th.items) if (!lessonById.has(l.id)) lessonById.set(l.id, l);
  const lessons = [...lessonById.values()];

  let books = SAMPLE ? [] : parseBooks(readJson(path.join(ROOT, 'books.json')));
  let bookSample = false;
  if (!books.length) {
    const sampleBooks = parseBooks(readJson(path.join(ROOT, '_books.sample.json')));
    books = [...parseBooks(readJson(path.join(ROOT, 'books.json'))), ...sampleBooks];
    bookSample = sampleBooks.length > 0;
  }
  books = [...new Map(books.map((b) => [b.id, b])).values()];
  const docs = [...new Map(parseDocs(readJson(path.join(ROOT, 'docs.json'))).map((x) => [x.id, x])).values()];

  return { collections, colById, entries, byId, byTopic, lessons, lessonById, books, docs, sample: { sources: src.sample, theory: th.sample, books: bookSample } };
}

function db(): Store {
  const now = Date.now();
  if (store && now - checkedAt < 10_000) return store;
  checkedAt = now;
  const sig = currentSignature();
  if (!store || sig !== signature) {
    store = build();
    signature = sig;
  }
  return store;
}

// ---------- queries ----------
export const stats = () => {
  const s = db();
  return { collections: s.collections.length, problems: s.entries.length, lessons: s.lessons.length, books: s.books.length, docs: s.docs.length, sample: s.sample };
};
export const collections = () => db().collections;
export const collection = (id: string) => db().colById.get(id);
export const problemEntry = (id: string) => db().byId.get(id);
export const topicCount = (t: TopicId) => db().byTopic.get(t)?.length ?? 0;
export const lessons = () => db().lessons;
export const lesson = (id: string) => db().lessonById.get(id);
export const books = () => db().books;
export const docs = () => db().docs;

export type ProblemQuery = { topic?: TopicId; grade?: number; kind?: Kind; year?: number; q?: string };
export function queryProblems(f: ProblemQuery, page: number, per: number) {
  const s = db();
  let list = f.topic ? (s.byTopic.get(f.topic) ?? []) : s.entries;
  const words = f.q ? fold(f.q).split(/\s+/).filter(Boolean) : [];
  if (f.grade || f.kind || f.year || words.length)
    list = list.filter(
      (e) =>
        (!f.grade || e.col.grade === f.grade) &&
        (!f.kind || e.col.kind === f.kind) &&
        (!f.year || e.col.year === f.year) &&
        words.every((w) => e.norm.includes(w)),
    );
  const pages = Math.max(1, Math.ceil(list.length / per));
  const p = Math.min(Math.max(1, page), pages);
  return { total: list.length, page: p, pages, items: list.slice((p - 1) * per, p * per) };
}

export type CollectionQuery = { kind?: Kind; grade?: number; year?: number; province?: string; q?: string };
export function queryCollections(f: CollectionQuery, page: number, per: number) {
  const words = f.q ? fold(f.q).split(/\s+/).filter(Boolean) : [];
  const list = db().collections.filter(
    (c) =>
      (!f.kind || c.kind === f.kind) &&
      (!f.grade || c.grade === f.grade) &&
      (!f.year || c.year === f.year) &&
      (!f.province || c.province === f.province) &&
      (!words.length || words.every((w) => fold(`${c.title} ${c.province ?? ''} ${c.sourceName}`).includes(w))),
  );
  const pages = Math.max(1, Math.ceil(list.length / per));
  const p = Math.min(Math.max(1, page), pages);
  return { total: list.length, page: p, pages, items: list.slice((p - 1) * per, p * per) };
}

export function facets() {
  const s = db();
  const years = new Set<number>();
  const provinces = new Set<string>();
  for (const c of s.collections) {
    if (c.year) years.add(c.year);
    if (c.province) provinces.add(c.province);
  }
  return { years: [...years].sort((a, b) => b - a), provinces: [...provinces].sort((a, b) => a.localeCompare(b, 'vi')) };
}

/** Deterministic "problem of the day" (Vietnam date). */
export function dailyProblem(date = new Date()) {
  const s = db();
  if (!s.entries.length) return undefined;
  const day = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }).format(date);
  let h = 2166136261;
  for (const ch of day) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return { entry: s.entries[(h >>> 0) % s.entries.length], day };
}

/** A few problems of the same topic from other collections, deterministic per id. */
export function related(id: string, n = 4) {
  const e = db().byId.get(id);
  if (!e) return [];
  const pool = (db().byTopic.get(e.problem.topics[0]) ?? []).filter((x) => x.col.id !== e.col.id);
  if (pool.length <= n) return pool;
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const start = h % pool.length;
  return Array.from({ length: n }, (_, i) => pool[(start + i * 7) % pool.length]).filter((x, i, a) => a.indexOf(x) === i);
}
