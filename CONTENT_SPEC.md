# toanthcs-hard — content spec (shared contract between crawlers and the web)

App: "Rùa Toán" — kho toán nâng cao THCS (HSG lớp 6–9, thi vào 10 chuyên, tạp chí, chuyên đề).
Web tối giản, từ ngữ thông dụng. Chỉ hiện đề bài (không lời giải, không độ khó); học sinh nộp bài bằng ảnh chụp (lưu trên máy).
5 chuyên đề: so-hoc, dai-so, bat-dang-thuc, hinh-hoc, to-hop (web tự gộp nghiem-nguyen → so-hoc, phuong-trinh → dai-so).

Stack: Next.js 16 (same versions as ../toanthcs), static JSON content in `content/`, no DB.
Math: markdown-lite + KaTeX (`$...$` inline, `$$...$$` display; never `\(` `\[`). Renderer = copy of ../toanthcs/lib/md.ts.

## Directory layout
```
content/
  sources/<source>.json    Collection[]   one file per crawler (toanmath-hsg.json, toanmath-chuyen.json, tapchi.json, ...)
  theory/<topic>.json      Lesson[]       "Bí kíp" — chuyên đề lý thuyết + ví dụ mẫu
  books.json               Book[]         sách miễn phí (metadata + link only)
  docs.json                Doc[]          tài liệu PDF theo chuyên đề (link về trang gốc)
scripts/                   crawlers / ingest pipelines (python3 + aiohttp, node for katex check)
.cache/                    downloaded PDFs, Gemini cache, logs — gitignored + vercelignored, never served
```
Files in `content/sources/` whose name starts with `_` are ignored by the web (use for WIP).
Write JSON atomically (tmp file + rename) — the web may read while a crawler writes.

## Types
```ts
type TopicId =
  | 'so-hoc'        // Số học: chia hết, đồng dư, số nguyên tố, ƯCLN/BCNN, số chính phương, chữ số
  | 'nghiem-nguyen' // Phương trình nghiệm nguyên, phương trình Diophantine
  | 'dai-so'        // Biến đổi đại số, hằng đẳng thức, căn thức, đa thức, phân thức, tính giá trị, dãy/tổng
  | 'phuong-trinh'  // Phương trình & hệ phương trình khó: vô tỉ, bậc cao, chứa tham số, Vi-ét nâng cao
  | 'bat-dang-thuc' // Bất đẳng thức, cực trị (min/max)
  | 'hinh-hoc'      // Hình học phẳng: tam giác, tứ giác, đường tròn, quỹ tích, dựng hình, hình học tổ hợp
  | 'to-hop'        // Tổ hợp – rời rạc: Dirichlet, bất biến, cực hạn, đếm, trò chơi, logic, đồ thị, tô màu

type Level = 1 | 2 | 3 | 4
// 1 Đai vàng  = khá / nâng cao cơ bản
// 2 Đai xanh  = giỏi cấp trường-huyện
// 3 Đai nâu   = HSG tỉnh / câu khó đề chuyên
// 4 Đai đen   = câu cuối đề chuyên/HSG tỉnh khó, cấp quốc gia/Olympic

type Problem = {
  id: string          // globally unique, slug: `${collection.id}-${labelSlug}`
  label: string       // "Bài 3a", "Câu 5", "T2/560"
  text: string        // đề bài, tự đủ nghĩa (chép lại giả thiết chung cho từng ý), hình vẽ mô tả bằng lời
  topics: TopicId[]   // 1–2
  // CẤM: không tạo hint / solution / answer (kể cả ví dụ trong bài giảng); level không dùng
}

type Collection = {
  id: string                      // slug, unique across all files (prefix by source, e.g. "tm-hsg9-2025-nghe-an")
  kind: 'hsg' | 'chuyen' | 'tapchi' | 'chuyende' | 'olympic'
  title: string                   // "Đề thi HSG Toán 9 cấp tỉnh 2024–2025 – Nghệ An"
  grade: 6 | 7 | 8 | 9 | 10       // 10 = thi vào lớp 10 chuyên
  year?: number                   // năm thi (năm học 2024-2025, thi tháng 3/2025 → 2025)
  province?: string               // có dấu
  sourceName: string              // "toanmath.com", "Tạp chí Toán học và Tuổi trẻ số 560", ...
  sourceUrl: string               // link bài gốc (KHÔNG link tới bản sao PDF của mình)
  problems: Problem[]
}

type Lesson = {
  id: string; topic: TopicId; level: Level
  title: string; summary: string  // 1–2 câu
  body: string                    // markdown-lite + KaTeX; dùng "## " cho mục, "- " cho list
  examples?: { text: string; solution: string }[]
}

type Doc = {
  id: string; topic: TopicId; title: string; author?: string
  grades: number[]; pages?: number; desc: string      // 1 câu ngắn tự viết
  url: string; pdf?: string; source: string            // trang gốc + link PDF trên chính trang gốc
}

type Book = {
  id: string; title: string; author?: string; publisher?: string
  grades: number[]; topics: TopicId[]; desc: string   // mô tả ngắn tự viết
  url: string; source: string                          // "sachhoc.com", ...
}
```

## Copyright rules (all crawlers)
- Official exam papers (đề thi HSG, tuyển sinh): problem statements may be reproduced; solutions are re-written (not pasted from the PDF's đáp án) and always credit `sourceUrl`.
- Magazines (THTT, Toán Tuổi Thơ): only short problem statements with attribution (issue, problem code, proposer if known); solutions are our own.
- Books (sachhoc.com etc.): catalog metadata + link only. Do not download, extract, or republish book contents.
- Never put PDFs/scans in `public/` or `content/`.
