import { db, device, json } from '@/lib/db';

const MAX_FILES = 6;
const MAX_BYTES = 150_000; // client sends grayscale ≤ 1000 px WebP/JPEG, usually 30–80 KB
const DAY_LIMIT = 60;

const row = (r: { id: string; problem_id: string; label: string; title: string; created_at: Date }) => ({
  id: r.id,
  pid: r.problem_id,
  label: r.label,
  title: r.title,
  at: new Date(r.created_at).getTime(),
});

// GET [?problem=id] → this device's photos (metadata only)
export async function GET(req: Request) {
  const dev = device(req);
  if (!dev) return json({ error: 'Thiếu mã thiết bị' }, 401);
  const problem = new URL(req.url).searchParams.get('problem');
  const sql = await db();
  const rows = await sql<{ id: string; problem_id: string; label: string; title: string; created_at: Date }[]>`
    select id, problem_id, label, title, created_at from thcs_hard.photos
    where device = ${dev} ${problem ? sql`and problem_id = ${problem}` : sql``}
    order by created_at desc limit 500`;
  return json({ photos: rows.map(row) });
}

// POST multipart: problem, label, title, images[]
export async function POST(req: Request) {
  const dev = device(req);
  if (!dev) return json({ error: 'Thiếu mã thiết bị' }, 401);
  const form = await req.formData().catch(() => null);
  if (!form) return json({ error: 'Dữ liệu không hợp lệ' }, 400);
  const problem = String(form.get('problem') || '').slice(0, 160);
  const label = String(form.get('label') || '').slice(0, 60);
  const title = String(form.get('title') || '').slice(0, 300);
  const files = form.getAll('images').filter((f): f is File => f instanceof File && f.size > 0);
  if (!/^[a-z0-9-]+$/.test(problem)) return json({ error: 'Thiếu mã bài' }, 400);
  if (!files.length) return json({ error: 'Chưa có ảnh' }, 400);
  if (files.length > MAX_FILES) return json({ error: `Tối đa ${MAX_FILES} ảnh một lần` }, 400);
  for (const f of files) {
    if (!/^image\/(webp|jpeg)$/.test(f.type)) return json({ error: 'Chỉ nhận ảnh' }, 400);
    if (f.size > MAX_BYTES) return json({ error: 'Ảnh quá lớn' }, 400);
  }
  const sql = await db();
  const [{ n }] = await sql`select count(*)::int as n from thcs_hard.photos where device = ${dev} and created_at > now() - interval '1 day'`;
  if (n + files.length > DAY_LIMIT) return json({ error: 'Hôm nay đã nộp quá nhiều ảnh' }, 429);
  const bufs = await Promise.all(files.map(async (f) => ({ mime: f.type, data: Buffer.from(await f.arrayBuffer()) })));
  const rows = await sql.begin((tx) =>
    Promise.all(
      bufs.map(
        (b) => tx<{ id: string; problem_id: string; label: string; title: string; created_at: Date }[]>`
          insert into thcs_hard.photos (device, problem_id, label, title, mime, bytes, data)
          values (${dev}, ${problem}, ${label}, ${title}, ${b.mime}, ${b.data.length}, ${b.data})
          returning id, problem_id, label, title, created_at`,
      ),
    ),
  );
  return json({ photos: rows.flat().map(row) });
}
