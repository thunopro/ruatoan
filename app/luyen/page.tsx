import type { Metadata } from 'next';
import Link from 'next/link';
import type { CSSProperties } from 'react';
import { queryProblems, type ProblemQuery } from '@/lib/content';
import { num, one } from '@/lib/text';
import { isKind, isTopic, TOPIC, TOPICS } from '@/lib/topics';
import { Empty, PageHead, Pager, ProblemCard, qs } from '../ui/bits';
import { DoneMarks } from '../ui/client';

type SP = Promise<Record<string, string | string[] | undefined>>;
const PER = 20;

export async function generateMetadata({ searchParams }: { searchParams: SP }): Promise<Metadata> {
  const t = one((await searchParams).topic);
  const title = isTopic(t) ? `Luyện bài: ${TOPIC[t].name}` : 'Luyện bài';
  const description = 'Bài toán nâng cao THCS theo chuyên đề, lớp và năm.';
  return { title, description, openGraph: { title, description } };
}

export default async function Luyen({ searchParams }: { searchParams: SP }) {
  const sp = await searchParams;
  const t = one(sp.topic);
  const k = one(sp.kind);
  const f: ProblemQuery = {
    topic: isTopic(t) ? t : undefined,
    grade: [6, 7, 8, 9, 10].includes(num(sp.grade) ?? 0) ? num(sp.grade) : undefined,
    kind: isKind(k) ? k : undefined,
    year: num(sp.year),
    q: one(sp.q).trim().slice(0, 80) || undefined,
  };
  const r = queryProblems(f, num(sp.page) ?? 1, PER);
  const params = { topic: f.topic, grade: f.grade, kind: f.kind, year: f.year, q: f.q };
  const topic = f.topic ? TOPIC[f.topic] : undefined;

  return (
    <>
      <PageHead title={topic ? topic.name : 'Luyện bài'} clan={topic?.clan ?? 'xich'} mood="focus" />

      <div className="topic-tabs" role="list">
        <Link role="listitem" href={qs('/luyen', { ...params, topic: undefined })} className={!f.topic ? 'on' : undefined}>
          Tất cả
        </Link>
        {TOPICS.map((x) => (
          <Link role="listitem" key={x.id} href={qs('/luyen', { ...params, topic: x.id })} className={f.topic === x.id ? 'on' : undefined} style={{ '--t': x.color, '--ti': x.ink } as CSSProperties}>
            <b aria-hidden="true">{x.icon}</b> {x.name}
          </Link>
        ))}
      </div>


      <p className="result-count">
        <b>{r.total.toLocaleString('vi-VN')}</b> bài{r.pages > 1 ? ` · trang ${r.page}/${r.pages}` : ''}
      </p>

      {r.items.length ? (
        <div className="plist">
          {r.items.map((e) => (
            <ProblemCard key={e.problem.id} problem={e.problem} col={e.col} />
          ))}
        </div>
      ) : (
        <Empty>
          <h2>Không có bài nào</h2>
          <p>
            <Link href="/luyen">Xóa bộ lọc</Link>
          </p>
        </Empty>
      )}
      <Pager base="/luyen" params={params} page={r.page} pages={r.pages} />
      <DoneMarks key={qs('/luyen', { ...params, page: r.page })} />
    </>
  );
}
