import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import type { CSSProperties } from 'react';
import { problemEntry, related } from '@/lib/content';
import { plain, snippet } from '@/lib/text';
import { CLANS, gradeName } from '@/lib/topics';
import { Turtle } from '../../ui/art';
import { Chip, clanOf, Md, Stamp } from '../../ui/bits';
import { DoneMarks, SubmitBox } from '../../ui/client';

type P = { params: Promise<{ id: string }> };
export const revalidate = 86400;

export async function generateMetadata({ params }: P): Promise<Metadata> {
  const e = problemEntry(decodeURIComponent((await params).id));
  if (!e) return { title: 'Không tìm thấy bài' };
  const title = `${e.problem.label} — ${e.col.title}`;
  const description = plain(e.problem.text, 160);
  return { title, description, openGraph: { title, description, type: 'article' } };
}

export default async function Bai({ params }: P) {
  const { id } = await params;
  const e = problemEntry(decodeURIComponent(id));
  if (!e) notFound();
  const { problem: p, col, index } = e;
  const prev = col.problems[index - 1];
  const next = col.problems[index + 1];
  const clan = clanOf(p);
  const rel = related(p.id, 4);

  return (
    <article className="bai" style={{ '--c': CLANS[clan].mask, '--cd': CLANS[clan].deep } as CSSProperties}>
      <nav className="crumbs" aria-label="Vị trí">
        <Link href="/luyen">Luyện bài</Link> <span aria-hidden="true">›</span> <Link href={`/de/${col.id}`}>{col.title}</Link>
      </nav>

      <header className="bai-head">
        <Turtle clan={clan} size={96} mood="focus" className="bai-art" />
        <div>
          <div className="row">
            <Stamp kind={col.kind} />
            <span className="small muted">
              {gradeName(col.grade)}
              {col.year ? ` · ${col.year}` : ''}
              {col.province ? ` · ${col.province}` : ''}
            </span>
          </div>
          <h1>{p.label}</h1>
          <div className="row">
            {p.topics.map((t) => (
              <Chip key={t} id={t} link />
            ))}
          </div>
        </div>
      </header>

      <div className="scroll big">
        <Md src={p.text} />
      </div>

      <SubmitBox rec={{ pid: p.id, label: p.label, title: col.title }} />

      <nav className="prevnext" aria-label="Bài trước / sau trong đề">
        {prev ? (
          <Link href={`/bai/${prev.id}`} className="pn prev">
            <small>← Bài trước</small>
            <b>{prev.label}</b>
          </Link>
        ) : (
          <span />
        )}
        <Link href={`/de/${col.id}`} className="pn mid">
          <small>
            Bài {index + 1}/{col.problems.length}
          </small>
          <b>Cả đề</b>
        </Link>
        {next ? (
          <Link href={`/bai/${next.id}`} className="pn next">
            <small>Bài sau →</small>
            <b>{next.label}</b>
          </Link>
        ) : (
          <span />
        )}
      </nav>

      <p className="source">
        Nguồn:{' '}
        {col.sourceUrl ? (
          <a href={col.sourceUrl} target="_blank" rel="noopener nofollow">
            {col.sourceName} ↗
          </a>
        ) : (
          col.sourceName
        )}
      </p>

      {rel.length ? (
        <section>
          <h2 className="sec">Bài cùng chuyên đề</h2>
          <div className="mini-list">
            {rel.map((x) => (
              <Link key={x.problem.id} href={`/bai/${x.problem.id}`} className="mini" data-pid={x.problem.id}>
                <b>{x.problem.label}</b>
                <div className="md mini-text" dangerouslySetInnerHTML={{ __html: snippet(x.problem.text, 110).html }} />
                <small className="muted">{x.col.title}</small>
              </Link>
            ))}
          </div>
          <DoneMarks key={p.id} />
        </section>
      ) : null}
    </article>
  );
}
