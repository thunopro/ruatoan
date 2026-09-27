import type { Metadata } from 'next';
import Link from 'next/link';
import type { CSSProperties } from 'react';
import { books } from '@/lib/content';
import { one } from '@/lib/text';
import { isTopic, TOPICS } from '@/lib/topics';
import { BookRow, ByStage, Empty, PageHead, qs } from '../ui/bits';

type SP = Promise<Record<string, string | string[] | undefined>>;
export const metadata: Metadata = { title: 'Sách & tạp chí', description: 'Sách và tạp chí toán nổi tiếng từ Việt Nam, Nga, Canada…, xếp từ nền tảng đến chuyên sâu.' };

export default async function Sach({ searchParams }: { searchParams: SP }) {
  const t = one((await searchParams).topic);
  const topic = isTopic(t) ? t : undefined;
  const all = books();
  const list = all.filter((b) => !topic || b.topics.includes(topic));
  const mags = list.filter((b) => b.kind === 'magazine');
  const bks = list.filter((b) => b.kind !== 'magazine');

  return (
    <>
      <PageHead title="Sách & tạp chí" clan="cam" />
      <div className="topic-tabs">
        <Link href="/sach" className={!topic ? 'on' : undefined}>
          Tất cả
        </Link>
        {TOPICS.filter((x) => all.some((b) => b.topics.includes(x.id))).map((x) => (
          <Link key={x.id} href={qs('/sach', { topic: x.id })} className={topic === x.id ? 'on' : undefined} style={{ '--t': x.color, '--ti': x.ink } as CSSProperties}>
            <b aria-hidden="true">{x.icon}</b> {x.name}
          </Link>
        ))}
      </div>
      {mags.length ? (
        <section>
          <h2 className="sec">Tạp chí</h2>
          <ul className="docs">
            {mags.map((b) => (
              <BookRow key={b.id} book={b} />
            ))}
          </ul>
        </section>
      ) : null}
      {bks.length ? (
        <section>
          <h2 className="sec">Sách</h2>
          <ByStage items={bks} row={(b) => <BookRow key={b.id} book={b} />} />
        </section>
      ) : null}
      {!list.length ? (
        <Empty>
          <h2>Chưa có sách</h2>
        </Empty>
      ) : null}
    </>
  );
}
