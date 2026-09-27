import Link from 'next/link';
import type { CSSProperties } from 'react';
import { collections, dailyProblem, docs, lessons, stats, topicCount } from '@/lib/content';
import { TOPICS } from '@/lib/topics';
import { Turtle } from './ui/art';
import { Chip, clanOf, CollectionCard, Md } from './ui/bits';

export const revalidate = 3600;

const nf = new Intl.NumberFormat('vi-VN');

export default function Home() {
  const s = stats();
  const daily = dailyProblem();
  const latest = collections().slice(0, 6);
  const ls = lessons();
  const ds = docs();

  return (
    <>
      <section className="hero">
        <div className="hero-text">
          <p className="kicker">Toán nâng cao THCS</p>
          <h1 className="logo-big">
            Rùa <span>Toán</span>
          </h1>
          <p className="lead">Đề HSG lớp 6–9, đề vào 10 chuyên và tài liệu theo chuyên đề.</p>
          <div className="row">
            <Link href="/luyen" className="btn big">
              Luyện bài
            </Link>
            <Link href="/chuyen-de" className="btn ghost big">
              Chuyên đề
            </Link>
          </div>
        </div>
        <div className="hero-art" aria-hidden="true">
          <Turtle clan="xich" size={128} className="t t2" mood="focus" />
          <Turtle clan="lam" size={176} className="t t1" />
          <Turtle clan="tu" size={128} className="t t3" />
          <Turtle clan="cam" size={112} className="t t4" />
        </div>
      </section>

      <section className="stats" aria-label="Số liệu">
        {[
          { n: s.problems, l: 'bài toán', href: '/luyen' },
          { n: s.collections, l: 'đề thi', href: '/de' },
          { n: s.docs, l: 'tài liệu PDF', href: '/chuyen-de' },
          { n: s.books, l: 'sách', href: '/sach' },
        ].map((x) => (
          <Link key={x.href} href={x.href} className="stat">
            <b>{nf.format(x.n)}</b>
            <span>{x.l}</span>
          </Link>
        ))}
      </section>

      {daily ? (
        <section className="mission" style={{ '--c': TOPICS.find((t) => t.id === daily.entry.problem.topics[0])?.color } as CSSProperties}>
          <div className="mission-side">
            <p className="mission-tag">Bài hôm nay</p>
            <Turtle clan={clanOf(daily.entry.problem)} size={110} mood="focus" />
            <p className="small">{daily.day.split('-').reverse().join('/')}</p>
          </div>
          <div className="mission-main">
            <div className="row">
              <b className="plabel">{daily.entry.problem.label}</b>
              {daily.entry.problem.topics.map((t) => (
                <Chip key={t} id={t} link />
              ))}
            </div>
            <div className="scroll">
              <Md src={daily.entry.problem.text} />
            </div>
            <div className="row">
              <Link href={`/bai/${daily.entry.problem.id}`} className="btn">
                Làm bài
              </Link>
              <span className="small muted">{daily.entry.col.title}</span>
            </div>
          </div>
        </section>
      ) : null}

      <h2 className="sec">Chuyên đề</h2>
      <div className="topics">
        {TOPICS.map((t) => (
          <Link key={t.id} href={`/chuyen-de/${t.id}`} className="topic" style={{ '--t': t.color, '--ti': t.ink } as CSSProperties}>
            <b className="topic-icon" aria-hidden="true">
              {t.icon}
            </b>
            <span>
              <strong>{t.name}</strong>
              <small>
                {nf.format(topicCount(t.id))} bài · {ls.filter((l) => l.topic === t.id).length} bài giảng · {ds.filter((d) => d.topic === t.id).length} tài liệu
              </small>
            </span>
          </Link>
        ))}
      </div>

      {latest.length ? (
        <>
          <div className="sec-row">
            <h2 className="sec">Đề mới</h2>
            <Link href="/de" className="btn ghost sm">
              Xem tất cả →
            </Link>
          </div>
          <div className="grid">
            {latest.map((c) => (
              <CollectionCard key={c.id} col={c} />
            ))}
          </div>
        </>
      ) : null}
    </>
  );
}
