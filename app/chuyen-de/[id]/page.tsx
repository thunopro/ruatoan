import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import type { CSSProperties } from 'react';
import { books, docs, lessons, topicCount } from '@/lib/content';
import { isTopic, TOPIC, TOPICS } from '@/lib/topics';
import { BookRow, ByStage, DocRow, PageHead, Tx } from '../../ui/bits';

type P = { params: Promise<{ id: string }> };

export const generateStaticParams = () => TOPICS.map((t) => ({ id: t.id }));
export const dynamicParams = false;

export async function generateMetadata({ params }: P): Promise<Metadata> {
  const { id } = await params;
  if (!isTopic(id)) return { title: 'Không tìm thấy chuyên đề' };
  return { title: `Chuyên đề ${TOPIC[id].name}`, description: `${TOPIC[id].desc} Bài giảng, tài liệu PDF và bài tập.` };
}

export default async function Topic({ params }: P) {
  const { id } = await params;
  if (!isTopic(id)) notFound();
  const t = TOPIC[id];
  const ls = lessons().filter((l) => l.topic === id);
  const ds = docs().filter((d) => d.topic === id);
  const bs = books().filter((b) => b.topics.includes(id));
  const n = topicCount(id);

  return (
    <div className="topic-page" style={{ '--t': t.color, '--ti': t.ink } as CSSProperties}>
      <nav className="crumbs" aria-label="Vị trí">
        <Link href="/chuyen-de">Chuyên đề</Link>
      </nav>
      <PageHead title={t.name} clan={t.clan}>
        <p className="lead">{t.desc}</p>
        {n ? (
          <Link href={`/luyen?topic=${id}`} className="btn">
            Luyện {n} bài
          </Link>
        ) : null}
      </PageHead>

      {ls.length ? (
        <section>
          <h2 className="sec">Bài giảng</h2>
          <div className="grid">
            {ls.map((l, i) => (
              <Link key={l.id} href={`/ly-thuyet/${l.id}`} className="lcard">
                <span className="lcard-no">{String(i + 1).padStart(2, '0')}</span>
                <h3>
                  <Tx src={l.title} />
                </h3>
                {l.summary ? (
                  <p className="small">
                    <Tx src={l.summary} />
                  </p>
                ) : null}
              </Link>
            ))}
          </div>
        </section>
      ) : null}

      {ds.length ? (
        <section>
          <h2 className="sec">Tài liệu PDF</h2>
          <ByStage items={ds} row={(d) => <DocRow key={d.id} doc={d} />} />
        </section>
      ) : null}

      {bs.length ? (
        <section>
          <h2 className="sec">Sách</h2>
          <ByStage items={bs} row={(b) => <BookRow key={b.id} book={b} />} />
        </section>
      ) : null}
    </div>
  );
}
