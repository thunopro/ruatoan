import { db, device, json } from '@/lib/db';

type Ctx = { params: Promise<{ id: string }> };
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

// Image bytes. The id is a random uuid, so the URL itself is the capability.
export async function GET(_req: Request, ctx: Ctx) {
  const { id } = await ctx.params;
  if (!UUID.test(id)) return new Response('not found', { status: 404 });
  const sql = await db();
  const [r] = await sql`select mime, data from thcs_hard.photos where id = ${id}`;
  if (!r) return new Response('not found', { status: 404 });
  return new Response(r.data, { headers: { 'Content-Type': r.mime, 'Cache-Control': 'private, max-age=31536000, immutable' } });
}

export async function DELETE(req: Request, ctx: Ctx) {
  const dev = device(req);
  const { id } = await ctx.params;
  if (!dev || !UUID.test(id)) return json({ error: 'Không hợp lệ' }, 400);
  const sql = await db();
  const r = await sql`delete from thcs_hard.photos where id = ${id} and device = ${dev}`;
  return json({ ok: r.count > 0 });
}
