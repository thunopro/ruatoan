import { createHash } from 'node:crypto';
import postgres from 'postgres';

/** Shares the Neon database of toan-vao-10; everything of this app lives in schema thcs_hard. */
type G = { __sql?: postgres.Sql; __ready?: Promise<void> };
const g = globalThis as unknown as G;

function client() {
  if (!g.__sql) {
    const url = process.env.DATABASE_URL || process.env.POSTGRES_URL;
    if (!url) throw new Error('DATABASE_URL is not set');
    g.__sql = postgres(url, { max: 3, prepare: false, idle_timeout: 20, onnotice: () => {} });
  }
  return g.__sql;
}

/** Only ever append. Index + 1 is the schema version stored in thcs_hard.meta. */
const MIGRATIONS: string[][] = [
  [
    `create table if not exists thcs_hard.photos (
      id uuid primary key default gen_random_uuid(),
      device text not null,
      problem_id text not null,
      label text not null default '',
      title text not null default '',
      mime text not null,
      bytes int not null,
      data bytea not null,
      created_at timestamptz not null default now())`,
    `create index if not exists photos_device on thcs_hard.photos (device, created_at)`,
    `create index if not exists photos_problem on thcs_hard.photos (problem_id)`,
  ],
];

async function schemaVersion(q: postgres.Sql | postgres.TransactionSql) {
  const [{ ok }] = await q`select to_regclass('thcs_hard.meta') is not null as ok`;
  if (!ok) return 0;
  const [row] = await q`select value from thcs_hard.meta where key = 'schema'`;
  return row ? Number(row.value) : 0;
}

export async function db() {
  const sql = client();
  if (!g.__ready) {
    g.__ready = (async () => {
      if ((await schemaVersion(sql)) >= MIGRATIONS.length) return;
      await sql.begin(async (tx) => {
        await tx`select pg_advisory_xact_lock(4211)`;
        await tx`create schema if not exists thcs_hard`;
        await tx`create table if not exists thcs_hard.meta (key text primary key, value text not null)`;
        for (let v = await schemaVersion(tx); v < MIGRATIONS.length; v++) for (const s of MIGRATIONS[v]) await tx.unsafe(s);
        await tx`insert into thcs_hard.meta (key, value) values ('schema', ${String(MIGRATIONS.length)})
          on conflict (key) do update set value = excluded.value`;
      });
    })().catch((e) => {
      g.__ready = undefined;
      throw e;
    });
  }
  await g.__ready;
  return sql;
}

/** Anonymous device token (random, kept in the browser) → stored only as a hash. */
export function device(req: Request) {
  const t = req.headers.get('x-device') ?? '';
  return /^[A-Za-z0-9-]{20,64}$/.test(t) ? createHash('sha256').update(t).digest('hex') : null;
}

export const json = (data: unknown, status = 200) => Response.json(data, { status, headers: { 'Cache-Control': 'no-store' } });
