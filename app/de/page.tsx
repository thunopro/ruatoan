import type { Metadata } from 'next';
import Link from 'next/link';
import { facets, queryCollections, type CollectionQuery } from '@/lib/content';
import { num, one } from '@/lib/text';
import { isKind, KINDS, type Kind } from '@/lib/topics';
import { CollectionCard, Empty, PageHead, Pager, qs } from '../ui/bits';

type SP = Promise<Record<string, string | string[] | undefined>>;
const PER = 24;

export async function generateMetadata({ searchParams }: { searchParams: SP }): Promise<Metadata> {
  const k = one((await searchParams).kind);
  const title = isKind(k) ? KINDS[k].long : 'Đề thi';
  const description = 'Đề HSG lớp 6–9, đề vào 10 chuyên, tạp chí và Olympic.';
  return { title, description, openGraph: { title, description } };
}

export default async function De({ searchParams }: { searchParams: SP }) {
  const sp = await searchParams;
  const k = one(sp.kind);
  const fc = facets();
  const prov = one(sp.province);
  const f: CollectionQuery = {
    kind: isKind(k) ? k : undefined,
    grade: [6, 7, 8, 9, 10].includes(num(sp.grade) ?? 0) ? num(sp.grade) : undefined,
    year: num(sp.year),
    province: fc.provinces.includes(prov) ? prov : undefined,
    q: one(sp.q).trim().slice(0, 80) || undefined,
  };
  const r = queryCollections(f, num(sp.page) ?? 1, PER);
  const params = { kind: f.kind, grade: f.grade, year: f.year, province: f.province, q: f.q };

  return (
    <>
      <PageHead title="Đề thi" clan="tu" />

      <div className="topic-tabs kinds" role="list">
        <Link role="listitem" href={qs('/de', { ...params, kind: undefined, grade: undefined })} className={!f.kind ? 'on' : undefined}>
          Tất cả
        </Link>
        {(Object.keys(KINDS) as Kind[]).map((x) => (
          <Link role="listitem" key={x} href={qs('/de', { ...params, kind: x, grade: undefined })} className={f.kind === x ? 'on' : undefined}>
            {KINDS[x].name}
          </Link>
        ))}
      </div>

      {f.kind === 'hsg' ? (
        <div className="topic-tabs" role="list">
          <Link role="listitem" href={qs('/de', { ...params, grade: undefined })} className={!f.grade ? 'on' : undefined}>
            Tất cả lớp
          </Link>
          {[6, 7, 8, 9].map((g) => (
            <Link role="listitem" key={g} href={qs('/de', { ...params, grade: g })} className={f.grade === g ? 'on' : undefined}>
              Lớp {g}
            </Link>
          ))}
        </div>
      ) : null}

      <p className="result-count">
        <b>{r.total.toLocaleString('vi-VN')}</b> đề{r.pages > 1 ? ` · trang ${r.page}/${r.pages}` : ''}
      </p>
      {r.items.length ? (
        <div className="grid">
          {r.items.map((c) => (
            <CollectionCard key={c.id} col={c} />
          ))}
        </div>
      ) : (
        <Empty>
          <h2>Không có đề nào</h2>
          <p>
            <Link href="/de">Xóa bộ lọc</Link>
          </p>
        </Empty>
      )}
      <Pager base="/de" params={params} page={r.page} pages={r.pages} />
    </>
  );
}
