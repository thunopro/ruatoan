import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import type { CSSProperties } from 'react';
import { lesson, lessons } from '@/lib/content';
import { plain } from '@/lib/text';
import { TOPIC } from '@/lib/topics';
import { Turtle } from '../../ui/art';
import { Md, Tx } from '../../ui/bits';

type P = { params: Promise<{ id: string }> };
export const revalidate = 86400;

export async function generateMetadata({ params }: P): Promise<Metadata> {
  const l = lesson(decodeURIComponent((await params).id));
  if (!l) return { title: 'Không tìm thấy bài giảng' };
  const title = plain(l.title, 90);
  const description = plain(l.summary, 160);
  return { title, description, openGraph: { title, description, type: 'article' } };
}

export default async function Lesson({ params }: P) {
  const l = lesson(decodeURIComponent((await params).id));
  if (!l) notFound();
  const t = TOPIC[l.topic];
  const siblings = lessons().filter((x) => x.topic === l.topic);
  return (
    <article className="lesson" style={{ '--t': t.color, '--ti': t.ink } as CSSProperties}>
      <nav className="crumbs" aria-label="Vị trí">
        <Link href="/chuyen-de">Chuyên đề</Link> <span aria-hidden="true">›</span> <Link href={`/chuyen-de/${t.id}`}>{t.name}</Link>
      </nav>
      <header className="bai-head">
        <Turtle clan={t.clan} size={96} className="bai-art" />
        <div>
          <p className="kicker">{t.name}</p>
          <h1>
            <Tx src={l.title} />
          </h1>
        </div>
      </header>
      <div className="lesson-layout">
        <div>
          <div className="scroll big">
            <Md src={l.body} />
          </div>
          {l.examples?.length ? (
            <section>
              <h2 className="sec">Bài tập áp dụng</h2>
              <ol className="de-list">
                {l.examples.map((ex, i) => (
                  <li key={i} className="scroll prob" style={{ '--c': t.color } as CSSProperties}>
                    <div className="prob-head">
                      <b className="plabel">Bài {i + 1}</b>
                    </div>
                    <Md src={ex.text} />
                  </li>
                ))}
              </ol>
            </section>
          ) : null}
          <div className="row">
            <Link href={`/luyen?topic=${t.id}`} className="btn big">
              Luyện bài {t.name}
            </Link>
          </div>
        </div>
        {siblings.length > 1 ? (
          <aside className="panel dark side">
            <h2 className="panel-title">{t.name}</h2>
            <ol className="side-list">
              {siblings.map((x) => (
                <li key={x.id}>
                  {x.id === l.id ? (
                    <b aria-current="page">
                      <Tx src={x.title} />
                    </b>
                  ) : (
                    <Link href={`/ly-thuyet/${x.id}`}>
                      <Tx src={x.title} />
                    </Link>
                  )}
                </li>
              ))}
            </ol>
          </aside>
        ) : null}
      </div>
    </article>
  );
}
