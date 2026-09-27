# REVIEW — ruatoan ("Ninja Rùa Toán")

Reviewed 2026-09-17 ~16:40–17:00 against the working tree (in-flight). Nothing else was edited.
State at review time: `content/sources` = 3 collections / 40 problems (toanmath-hsg 1, toanmath-chuyen 2), catalog 1780 exams,
ingest stopped on Flash quota, Claude lane has 1 result + 6 open claims.

Priority: **P0** = fix before/at launch (data loss, wrong content, won't scale); **P1** = this week; **P2** = nice to have.

---

## 0. Top P0 (short)

| # | Problem | File(s) |
|---|---------|---------|
| 1 | Claude-lane results are never merged into content | `scripts/exams/ingest.py` (`cached_only`, `extract`) |
| 2 | `ingest.py --only/--limit` overwrites the *other* output file with `[]` | `scripts/exams/ingest.py` `write_outputs` |
| 3 | Every lambda parses the whole corpus (layout calls `stats()`), ~30 MB JSON × every function bundle | `lib/content.ts`, `app/layout.tsx`, `next.config.ts` → new `scripts/build-index.mjs` |
| 4 | Exam solutions for level 3–4 are never verified (chuyên đề + tạp chí are) | `scripts/exams/ingest.py` (+ reuse `scripts/tapchi/solve.py`) |
| 5 | Level inflation: a *trường THCS* HSG paper came out 6×L3 + 3×L4 of 13 | prompts in `scripts/lib/common.py` `LEVEL_DESC`, `ingest.py`, `lane.py` |
| 6 | Magazine proposer is extracted then dropped (spec requires attribution) | `scripts/tapchi/run.py` `assemble` |

---

## 1. Performance

### P0-1 Build-time index + shards instead of "parse everything per cold start"
Now: `lib/content.ts#db()` reads all `content/sources/*.json`, builds `entries` with a `norm` string = folded copy of *full text* for
every problem, and keeps every hint/solution in memory. `app/layout.tsx` calls `stats()`, so **every route** (incl. `/dojo`, `/sach`,
not-found) triggers the full load. At ~30 MB JSON: JSON.parse ≈ 0.3–0.6 s + fold of 20k strings + ~120–200 MB heap per instance,
paid on every Vercel cold start, per function.

Do:
- New `scripts/build-index.mjs`, run as `"prebuild": "node scripts/build-index.mjs"` in `package.json`. Emits into `.data/` (gitignored, traced):
  - `.data/meta.json` — stats, facets (years, provinces), topic counts, daily-problem pool ids (~few KB). Layout/home read only this.
  - `.data/index.json` — one compact row per problem as arrays, not objects:
    `[id, colIdx, label, level, topicMask(bitmask 7 bits), hasSolution, snippetHtml]` + `collections: [id, kind, grade, year, province, title]`.
    Pre-rendered `snippetHtml` (KaTeX already run) removes all KaTeX work from `/luyen`. Est. 20k × ~350 B ≈ 7 MB raw, ~1.5 MB gz.
  - `.data/search.bin` or `search.json` — folded, **LaTeX-stripped** text (`plain()` + `fold()`), capped ~300 chars per problem; loaded lazily only when `q` is present.
  - `.data/col/<collectionId>.json` — full problems with **pre-rendered HTML** for text/hint/solution/answer. `/bai/[id]` and `/de/[id]` read one shard (problem id → collection id is a prefix lookup in index).
  - `.data/sorted/{de,kho}.json` — precomputed orderings (avoid `[...list].sort()` of 20k per request in `queryProblems`).
- `lib/content.ts`: split into `lib/index.ts` (index/meta, module-level singleton) and `lib/shard.ts` (LRU of ~50 collection shards). Keep the
  mtime/signature reload only when `process.env.NODE_ENV !== 'production'` (today it `readdir`+`stat`s every 10 s per instance in prod for nothing).
- `next.config.ts`: `outputFileTracingIncludes: { '/**': ['./content/**/*.json'] }` puts the whole corpus (incl. `_sample.json`) into
  every function. Change to `.data/**` only, and scope per route (`'/bai/[id]': ['./.data/col/**','./.data/index.json']`, `'/luyen': [...index, search]`).
- Dedupe (section 2) should run in the same prebuild so the web never sees duplicates.

### P0-2 KaTeX at build, not per request
`app/ui/bits.tsx` `Md` → `lib/md.ts` → `katex.renderToString` on every render; `/luyen` (dynamic because of `searchParams`) renders 20
snippets with KaTeX per request; `/bai/[id]` renders text+hint+solution+answer + 4 related snippets. Pre-render in `build-index.mjs`
(import `lib/md.ts` via `tsx`, or port to `.mjs` shared with `scripts/lib/katex_check.mjs`). Pages then only `dangerouslySetInnerHTML`.
Bonus: KaTeX (≈260 KB) is no longer needed in the server bundle at runtime.

### P1 Static generation & caching
- `/bai/[id]` and `/de/[id]` have `revalidate = 86400` but no `generateStaticParams` → every first hit is an on-demand render on a cold
  lambda. Add `generateStaticParams` for all collections (`/de`, ~2k pages) and for the top N problems (e.g. level ≥ 2 with solution);
  leave the rest ISR. Content only changes on deploy → `export const dynamicParams = true; revalidate = false` is fine.
- `/luyen`: when there is no `q`, the result depends only on (topic, level, grade, kind, year, sort, page) — fine to compute from index in < 2 ms; add
  `Cache-Control: s-maxage=3600, stale-while-revalidate=86400` via `headers()` in `next.config.ts` for `/luyen` and `/de` so the CDN absorbs traffic.
- `app/bai/[id]/page.tsx` `generateMetadata` uses `(await params).id` without `decodeURIComponent` while the page decodes — make consistent (ids are ASCII slugs; just drop decoding in both or decode in both).
- `facets()` iterates all collections each `/luyen` request → put in `meta.json`.

### P1 Search without diacritics
- Current `norm` includes raw LaTeX (`\frac`, `\sqrt`), so `q=frac` matches everything and index size doubles. Strip with `plain()` before `fold()`.
- Add a tiny token → problem-id postings map (folded words ≥ 3 chars, top 30k tokens) in `.data/search.json`; intersect posting lists instead of
  `words.every(w => norm.includes(w))` over 20k strings. Keep substring fallback for 1–2 words.
- Support exact label search (`T2/560`, `Câu 5 Nghệ An 2024`) by indexing `label + province + year + kind name`.
- Synonyms folded map (tiny, hand-written): `bdt→bat dang thuc`, `pt→phuong trinh`, `hpt→he phuong trinh`, `ucln`, `bcnn`, `scp→so chinh phuong`, `tgnt→tu giac noi tiep`.

### P2 Bundle / fonts
- `app/layout.tsx`: Be Vietnam Pro loads 4 weights (400/500/700/800) + Bungee. Drop 500 or 800 (≈ 2 font files, vietnamese subset ~40–60 KB each).
- `katex/dist/katex.min.css` is global (~23 KB) — OK; make sure KaTeX woff2 are only fetched when math exists (they are, via @font-face). Add
  `<link rel="preload">` for `KaTeX_Main-Regular.woff2` and `KaTeX_Math-Italic.woff2` on `/bai` and `/de` only.
- `app/ui/client.tsx` `Nav` subscribes to progress on every page — fine, but `SolvedMarks` walking `[data-pid]` DOM is fine too; no action.

### P1 Pipeline throughput
- **KaTeX checker spawns a `node` process per call**: `ingest.py fix_strings` calls `katex_check` once per collection *plus once per repaired
  string*; `lane.py` once per save. With CONC=28 that is hundreds of node startups (~80 ms each). Make `scripts/lib/katex_check.mjs` support
  a long-running `--serve` mode (JSONL stdin/stdout) and keep one process per Python run (`scripts/lib/common.py` helper).
- `scripts/exams/ingest.py` docstring says `CONC default 5`, code says `28` — fix doc; with free-tier ~20 req/day per (key, model), 28 parallel just burns 429 retries. Size CONC ≈ live slots (`len(keys) × len(FLASH)`), exposed from `gemini.py`.
- `write_outputs` re-dedupes and rewrites everything every 20 exams; dedupe is O(n²) inside (grade, year) groups. At 1780 exams fine, but move global dedupe to prebuild (section 2) and let ingest only write.
- `scripts/claude_lane/lane.py`:
  - `gemini_done()` does `d.iterdir()` over the whole cache dir **for every catalog entry** → O(catalog × cache files) on every `next`. Build the stem set once.
  - Claims never expire: 6 `.claim` files are open now; a crashed agent blocks an exam forever. Treat claims older than 45 min (mtime) as free.
  - Duplicate work: ingest (`extract`) doesn't check `.cache/exams/claude/<key>.json`, lane doesn't check in-flight Gemini. Add the check on the ingest side.
  - `prio()` / `years()` duplicated from ingest → import from ingest or `common.py`.

---

## 2. Data quality

### P0-1 Claude lane output is orphaned
`ingest.py cached_only()` only looks in `.cache/gemini/exams-v1*`; nothing reads `.cache/exams/claude/*.json`. Add
`CLAUDE_DIR / f'{entry_key(e)}.json'` as a third source in `cached_only` (after Flash, before lite? — Claude has no solutions by user
decision, so: Flash > Claude (statements) > lite). Mark such problems (no hint/solution) so a later solve pass picks them up (see P1-3).

### P0-2 Partial runs clobber output
`write_outputs()` writes **both** `toanmath-hsg.json` and `toanmath-chuyen.json` from `done_cols` of the current run. With `--only hsg9` the chuyen
file is rewritten as `[]`; with `--limit N` both shrink. Fix: load the existing file, replace only collections whose `sourceUrl`/id came from this
run's catalog subset, or skip writing a file when this run's catalog had no entries for it. (The log already shows a `WROTE {'hsg': (0, 0), 'chuyen': (0, 0)}` line.)

### P0-3 Level calibration
- Evidence: `tm-hsg9-...-truong-thcs-nguyen-truong-to-ha-noi` (school-level) → L3×6, L4×3 out of 13; the prompt itself says school/district papers are mostly 1–2.
- Three different rubrics: `ingest.py` rule 4 (no anchors), `chuyende/run.py` (good concrete anchors, line ~153), `tapchi/solve.py` ("thường 3 hoặc 4"),
  and Claude lane (none). Move the chuyên đề anchor list into `scripts/lib/common.py LEVEL_DESC` and use it everywhere.
- Add a deterministic post-pass in prebuild (or ingest): cap by paper scope — `truong`/`huyen`/`cum` in title → max L3, and at most 1–2 L4 per paper;
  HSG 6–7 → max L3 unless olympic. Log a per (kind, grade, scope) level histogram in `ingest_report.json` to eyeball drift.
- Silent defaults in `build_collections`: missing level → 2, missing topics → `['dai-so']`. Record `_defaulted` and exclude from topic pages until fixed.

### P0-4 Verify hard exam solutions
Only `chuyende/run.py verify()` and `tapchi/solve.py solve_verify()` verify. Exam extraction solves in one pass (often lite fallback, where `lite_ok`
only checks length ≥ 60 chars). Add `scripts/exams/verify.py`: for level ≥ 3 or `model in LITE`, run the tapchi verify prompt (FLASH, independent,
text-only, cached by `sha(text+solution)`); on fail → one fix round → else drop solution, keep hint. Store `verified: true|false` per problem.
Web: add optional `verified?: boolean` to `Problem` in `CONTENT_SPEC.md`/`lib/content.ts`; show a small "Lời giải chưa được kiểm chứng" note in `app/ui/client.tsx Reveal`.

### P1-1 Dedupe across sources
Today: web dedupes by id only; ingest dedupes within (isChuyen, grade, year) by token-set overlap; chuyên đề dedupes only within chuyên đề.
Misses: same exam reposted with a year off by one or classified hsg vs olympic; "Đề chung" vs "Đề chuyên" of the same province sharing questions;
chuyên đề PDFs copying exam problems; THTT problems reused in later HSG papers.
Do in `scripts/build-index.mjs` (or `scripts/dedupe.py` writing `content/dups.json`):
- Fingerprint = fold → strip `$`, `\left \right \dfrac→\frac`, whitespace, punctuation → 5-gram shingles → MinHash (64 perms) → LSH buckets; confirm Jaccard ≥ 0.8.
- Preference order for the canonical copy: exam with year+province > tapchi > olympic > chuyende; within same kind prefer `verified`, longer solution.
- Don't delete: keep problems in their collection (so `/de/[id]` is complete) but add `dupOf` → hidden from `/luyen`, counts, daily; `/bai/[id]` shows
  "Bài này cũng xuất hiện trong: …" (great for students: shows which đề reuse which classics).
- Whole-collection dup (≥ 70 % problems dupOf the same other collection) → hide the collection from `/de` listing, 301 its page to the canonical.

### P1-2 KaTeX / transcription errors that pass the checker
- `content/sources/toanmath-hsg.json` Bài 1.1: `\frac{x\sqrt{} + 5\sqrt{x} + 6}` — empty `\sqrt{}` renders fine, so `katex_check` passes, but
  the statement is wrong (Bài 1.2 has `x + 5\sqrt{x}`). Add lint rules to `scripts/lib/katex_check.mjs`: empty `\sqrt{}`, `\frac{}{…}`/`{…}{}`,
  `^{}`/`_{}`, unicode math outside `$` (`√ ≥ ≤ ≠ ∈ π`), `$$` inside a `- ` list line, trailing `:` at end of text (ingest prompt forbids it), text < 25 chars.
- `katex_check.mjs --file` only checks `text` and `answer`, not `hint`/`solution` → extend, and run it over all `content/**/*.json` in prebuild (fail build on > 0.5 % bad, warn otherwise).
- Cross-ý consistency check: sibling ý (`1.1`, `1.2`) must share the repeated giả thiết; flag when the shared prefix differs by a few chars (exactly the bug above).

### P1-3 Claude-lane statements need a solve pass
User decision: lane stores statements only. Add `scripts/exams/solve_missing.py` reusing `tapchi/solve.py solve_verify` (it already does solve → verify → keep
hint only if unverified) for problems without `solution`, run when Gemini quota resets (midnight PT).

### P1-4 Attribution
- `scripts/tapchi/run.py assemble`: `proposer` is extracted (schema line ~85, stored line ~283) but not written to items. Spec rule: "attribution (issue,
  problem code, proposer)". Add `source?: string` (or `proposer?: string`) to `Problem` in spec + `lib/content.ts parseCollections`, render under the
  statement in `app/bai/[id]/page.tsx` and `app/de/[id]/page.tsx`.
- Tạp chí `sourceUrl` is the Google Drive scan (a third-party copy of the issue). Prefer `https://thtt.vn/` issue page when known; keep Drive as secondary.
- Exams: `sourceName: 'toanmath.com'` — also show the issuing body parsed from the title ("Sở GD&ĐT Vĩnh Long", "Trường THCS …") in the collection header.
- Chuyên đề: `sourceName` includes author — good; ensure the problem-level footer on `/bai` doesn't claim "Đề thi thuộc về sở GD" wording for chuyên đề.
- `kind: 'chuyen'` also contains "Toán chung / không chuyên" papers (see Vĩnh Long pair). Add `variant: 'chuyen'|'chung'` to Collection so the filter "vào 10 chuyên" can separate them — the không chuyên paper is mostly L1–2 and dilutes the section.

### P2
- `year` rule: school HSG in Sept 2026 of năm học 2026–2027 → 2026, provincial HSG of the same năm học in Mar 2027 → 2027. Display "năm học 2026–2027" (store `schoolYear`) to avoid users thinking these are different seasons.
- Province normalisation lives in ingest only (`PROV_FIX`); move to `common.py` and apply to tapchi/olympic too so the `/de` province facet isn't split.

---

## 3. Product ideas (for HSG students)

All feasible static + localStorage unless noted. Progress already lives in `app/ui/progress.ts` (`nrt:progress:v1`: `solved`, `days`).

### P1 (high value, low cost)
1. **Hint ladder instead of hint→solution jump** — `Reveal` in `app/ui/client.tsx` has 2 steps. Pipeline already produces `hint`; ask the verify pass to also emit `hint2` (key step / auxiliary construction) and show: Gợi ý 1 → Gợi ý 2 → Đáp số → Lời giải. Pizza reward scales down per rung used (store `usedHints` in `SolvedRec`) — this makes pizza/rank honest.
2. **Self-rating after solving + spaced repetition** — on "Đã giải" ask "Tự giải / Cần gợi ý / Xem lời giải". Store `{ease, due}` in progress (SM-2-lite: 1 d → 3 d → 7 d → 21 d). `/dojo` "Ôn lại hôm nay (n bài)". Pure localStorage; extend `progress.ts` with a v2 key + migration.
3. **Learning path per topic** (`/bi-kip/[id]` → `/luyen`): each Lesson gets `practice: problemId[]` chosen at build time (same topic, level = lesson.level … +1, verified, not dup) → "Bí kíp → 2 ví dụ mẫu → 5 bài đai vàng → 5 đai xanh → 3 đai nâu", unlock next belt when ≥ 60 % solved. Build in `scripts/build-index.mjs`, UI on `app/bi-kip/[id]/page.tsx`.
4. **Weakness radar in dojo** — `Dojo.tsx` already counts by topic; switch to *ratio* solved-without-solution / attempted per topic × level, 7-axis SVG radar, and a "Luyện điểm yếu" button → `/luyen?topic=<weakest>&level=<current+0>`. Needs attempts tracking (record "opened solution" as attempt).
5. **Timed mock exam mode** — `/de/[id]?thi=1`: hides hints/solutions, countdown (150' chuyên, 120'/150' HSG — derive from title or default 150), autosave scratch answers per problem in localStorage, at end shows solutions + self-scoring per ý → saved to dojo history. Only needs client component around existing `app/de/[id]/page.tsx`.
6. **Similar problems that are actually similar** — `related()` today = same first topic ± 1 level, pseudo-random. At build: TF-IDF over folded LaTeX-stripped text + LaTeX command bag (`\sqrt`, `\pmod`, `\widehat`) → top-5 cosine neighbours per problem within topic, stored in shard. Also expose dup/"xuất hiện ở đề khác" links from section 2.

### P2
7. **Daily ninja mission** — `dailyProblem()` gives one problem; make it 3 (one per belt near the user's rank, chosen client-side from a daily pool of ~50 ids in `meta.json`), streak already exists in `progress.ts`.
8. **Print/PDF** — `PrintButton` exists on `/de`. Add print CSS toggles "Đề không lời giải" / "Đề + lời giải", and a "Phiếu luyện tập" builder: pick N problems from `/luyen` filters (cart in localStorage) → `/in?ids=…` printable page. Teachers will share this.
9. **Share links / progress export** — `/dojo` export/import progress as a base64 code or QR (no DB); share "Mình vừa lên Đai nâu" OG image via `app/bai/[id]/opengraph-image.tsx` (static, per belt).
10. **SEO per problem** — `/bai/[id]` metadata exists; add `alternates.canonical` (canonical = dedupe master), JSON-LD `Quiz`/`LearningResource` with `educationalLevel`, `app/sitemap.ts` split into sitemap index per kind (20k URLs > single 50k limit fine but split for crawl budget), and `noindex` for problems without solution or with `dupOf`.
11. **Offline/PWA** — manifest + service worker caching visited `/bai` and `/de` pages + KaTeX fonts ("Tải cuộn đề để làm offline"). Useful on phones in class; `next-pwa`-free: hand-written `public/sw.js` with cache-first for `/_next/static` and stale-while-revalidate for pages.
12. **Error report per problem** — footer already asks users to report errors. A `mailto:`/Google Form prefilled with problem id is DB-free; a counter/queue needs a DB (Neon per `_shared/accounts.md`) — later.
13. **Cross-device sync, leaderboards, class groups** — need DB + auth (Google OAuth from `_shared`). Defer.
