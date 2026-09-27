import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import type { CSSProperties } from 'react';
import { collection } from '@/lib/content';
import { gradeName, KINDS } from '@/lib/topics';
import { Turtle } from '../../ui/art';
import { Chip, colorOf, Md, Stamp } from '../../ui/bits';
import { DoneMarks, PrintButton } from '../../ui/client';

type P = { params: Promise<{ id: string }> };
export const revalidate = 86400;

export async function generateMetadata({ params }: P): Promise<Metadata> {
  const c = collection(decodeURIComponent((await params).id));
  if (!c) return { title: 'Không tìm thấy đề' };
  const description = `${KINDS[c.kind].long} · ${gradeName(c.grade)}${c.year ? ` · ${c.year}` : ''} · ${c.problems.length} bài.`;
  return { title: c.title, description, openGraph: { title: c.title, description, type: 'article' } };
}

export default async function DePage({ params }: P) {
  const c = collection(decodeURIComponent((await params).id));
  if (!c) notFound();
  return (
    <article className="de">
      <nav className="crumbs noprint" aria-label="Vị trí">
        <Link href="/de">Đề thi</Link> <span aria-hidden="true">›</span> <Link href={`/de?kind=${c.kind}`}>{KINDS[c.kind].long}</Link>
      </nav>
      <header className="de-head">
        <Turtle clan="tu" size={90} className="noprint" />
        <div>
          <div className="row">
            <Stamp kind={c.kind} />
            <span className="small">
              {gradeName(c.grade)}
              {c.year ? ` · ${c.year}` : ''}
              {c.province ? ` · ${c.province}` : ''} · {c.problems.length} bài
            </span>
          </div>
          <h1>{c.title}</h1>
          <p className="source">
            Nguồn:{' '}
            {c.sourceUrl ? (
              <a href={c.sourceUrl} target="_blank" rel="noopener nofollow">
                {c.sourceName} ↗
              </a>
            ) : (
              c.sourceName
            )}
          </p>
          <div className="row noprint">
            {c.problems[0] ? (
              <Link href={`/bai/${c.problems[0].id}`} className="btn">
                Làm từng bài
              </Link>
            ) : null}
            <PrintButton />
          </div>
        </div>
      </header>

      <ol className="de-list">
        {c.problems.map((p) => (
          <li key={p.id} id={p.id} className="scroll prob" data-pid={p.id} style={{ '--c': colorOf(p) } as CSSProperties}>
            <div className="prob-head">
              <b className="plabel">{p.label}</b>
              <span className="chips noprint">
                {p.topics.map((t) => (
                  <Chip key={t} id={t} link />
                ))}
              </span>
              <span className="done-tag">Đã nộp</span>
              <Link href={`/bai/${p.id}`} className="prob-go noprint">
                Nộp bài →
              </Link>
            </div>
            <Md src={p.text} />
          </li>
        ))}
      </ol>
      <DoneMarks key={c.id} />
    </article>
  );
}
