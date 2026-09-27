import Link from 'next/link';
import type { CSSProperties, ReactNode } from 'react';
import type { Book, Collection, Doc, Problem } from '@/lib/content';
import { md } from '@/lib/md';
import { snippet } from '@/lib/text';
import { gradeName, KINDS, LANG_NAME, STAGES, TOPIC, type ClanId } from '@/lib/topics';
import { Turtle } from './art';

export const Md = ({ src, className = '' }: { src: string; className?: string }) => <div className={`md ${className}`} dangerouslySetInnerHTML={{ __html: md(src) }} />;
/** One-line text with $math$ (titles, summaries). */
export const Tx = ({ src }: { src: string }) => <span className="md inline" dangerouslySetInnerHTML={{ __html: md(src).replace(/^<p>|<\/p>$/g, '') }} />;

export function Chip({ id, link }: { id: string; link?: boolean }) {
  const t = TOPIC[id];
  if (!t) return null;
  const style = { '--c': t.color, '--ci': t.ink } as CSSProperties;
  const body = (
    <>
      <b aria-hidden="true">{t.icon}</b>
      {t.name}
    </>
  );
  return link ? (
    <Link href={`/luyen?topic=${t.id}`} className="chip" style={style}>
      {body}
    </Link>
  ) : (
    <span className="chip" style={style}>
      {body}
    </span>
  );
}

export const clanOf = (p: { topics: string[] }): ClanId => TOPIC[p.topics[0]]?.clan ?? 'lam';
export const colorOf = (p: { topics: string[] }) => TOPIC[p.topics[0]]?.color ?? '#b6ff3b';
const grades = (g: number[]) => {
  const l = g.filter((x) => x < 10);
  const r = l.length > 2 ? [`Lớp ${Math.min(...l)}–${Math.max(...l)}`] : l.map(gradeName);
  return [...r, ...(g.includes(10) ? ['Vào 10'] : [])].join(', ');
};

export function ProblemCard({ problem, col }: { problem: Problem; col: Collection }) {
  const s = snippet(problem.text, 230);
  return (
    <Link href={`/bai/${problem.id}`} className="pcard" data-pid={problem.id} style={{ '--c': colorOf(problem) } as CSSProperties}>
      <div className="pcard-top">
        <span className="plabel">{problem.label}</span>
        <span className="done-tag">Đã nộp</span>
      </div>
      <div className="md pcard-text" dangerouslySetInnerHTML={{ __html: s.html }} />
      <div className="pcard-foot">
        <span className="chips">
          {problem.topics.map((t) => (
            <Chip key={t} id={t} />
          ))}
        </span>
        <span className="pcard-src">{col.title}</span>
      </div>
    </Link>
  );
}

export function Stamp({ kind }: { kind: Collection['kind'] }) {
  return <span className={`stamp stamp-${kind}`}>{KINDS[kind].stamp}</span>;
}

export function CollectionCard({ col }: { col: Collection }) {
  return (
    <Link href={`/de/${col.id}`} className="ccard">
      <div className="ccard-head">
        <Stamp kind={col.kind} />
        <span className="ccard-meta">
          {gradeName(col.grade)}
          {col.year ? ` · ${col.year}` : ''}
        </span>
      </div>
      <h3>{col.title}</h3>
      <p className="muted small">{col.problems.length} bài</p>
    </Link>
  );
}

export function DocRow({ doc }: { doc: Doc }) {
  const meta = [doc.author, doc.pages ? `${doc.pages} trang` : '', grades(doc.grades), doc.lang ? LANG_NAME[doc.lang] : ''].filter(Boolean).join(' · ');
  return (
    <li className="doc">
      <span className="doc-icon" aria-hidden="true">
        PDF
      </span>
      <div className="doc-body">
        <h3>{doc.title}</h3>
        {meta ? <p className="small muted">{meta}</p> : null}
        {doc.desc ? <p className="small">{doc.desc}</p> : null}
      </div>
      <div className="doc-act">
        {doc.pdf ? (
          <a href={doc.pdf} target="_blank" rel="noopener nofollow" className="btn sm">
            Tải PDF
          </a>
        ) : null}
        <a href={doc.url} target="_blank" rel="noopener nofollow" className={`btn sm${doc.pdf ? ' ghost' : ''}`}>
          {doc.source || 'Trang gốc'} ↗
        </a>
      </div>
    </li>
  );
}

export function BookRow({ book: b }: { book: Book }) {
  const meta = [b.author, b.publisher, grades(b.grades), b.lang ? LANG_NAME[b.lang] : ''].filter(Boolean).join(' · ');
  return (
    <li className="doc">
      <span className={`doc-icon ${b.kind === 'magazine' ? 'mag-icon' : 'book-icon'}`} aria-hidden="true">
        {b.kind === 'magazine' ? 'BÁO' : 'SÁCH'}
      </span>
      <div className="doc-body">
        <h3>
          {b.title} {b.free ? <span className="free">Miễn phí</span> : null}
        </h3>
        {meta ? <p className="small muted">{meta}</p> : null}
        {b.desc ? <p className="small">{b.desc}</p> : null}
      </div>
      <div className="doc-act">
        <a href={b.url} target="_blank" rel="noopener nofollow" className="btn sm">
          {b.source || 'Trang gốc'} ↗
        </a>
      </div>
    </li>
  );
}

/** Items grouped Nền tảng → Nâng cao → Chuyên sâu (items without a stage go last). */
export function ByStage<T extends { id: string; stage?: number }>({ items, row }: { items: T[]; row: (x: T) => ReactNode }) {
  const groups = [...STAGES.map((s) => ({ ...s, list: items.filter((x) => x.stage === s.stage) })), { stage: 0, name: 'Khác', desc: '', list: items.filter((x) => !x.stage) }].filter((g) => g.list.length);
  if (groups.length === 1 && !groups[0].stage) return <ul className="docs">{items.map(row)}</ul>;
  return (
    <div className="stages">
      {groups.map((g) => (
        <div key={g.stage} className={`stage stage-${g.stage}`}>
          <h3 className="stage-title">
            {g.stage ? <b>{g.stage}</b> : null} {g.name} {g.desc ? <small>· {g.desc}</small> : null}
          </h3>
          <ul className="docs">{g.list.map(row)}</ul>
        </div>
      ))}
    </div>
  );
}

export function PageHead({ kicker, title, children, clan = 'lam', mood }: { kicker?: string; title: ReactNode; children?: ReactNode; clan?: ClanId; mood?: 'happy' | 'focus' | 'dizzy' }) {
  return (
    <header className="phead">
      <Turtle clan={clan} size={80} className="phead-art" mood={mood} />
      <div>
        {kicker ? <p className="kicker">{kicker}</p> : null}
        <h1>{title}</h1>
        {children}
      </div>
    </header>
  );
}

type Params = Record<string, string | number | undefined>;
export const qs = (base: string, p: Params) => {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== undefined && v !== '' && !(k === 'page' && v === 1)) u.set(k, String(v));
  const s = u.toString();
  return s ? `${base}?${s}` : base;
};

export function Pager({ base, params, page, pages }: { base: string; params: Params; page: number; pages: number }) {
  if (pages <= 1) return null;
  const set = new Set([1, pages, page - 2, page - 1, page, page + 1, page + 2].filter((x) => x >= 1 && x <= pages));
  const nums = [...set].sort((a, b) => a - b);
  return (
    <nav className="pager" aria-label="Phân trang">
      {page > 1 ? (
        <Link href={qs(base, { ...params, page: page - 1 })} rel="prev">
          ← Trước
        </Link>
      ) : (
        <span className="off">← Trước</span>
      )}
      {nums.map((n, i) => (
        <span key={n} className="pnum">
          {i > 0 && n - nums[i - 1] > 1 ? <span className="gap">…</span> : null}
          {n === page ? (
            <b aria-current="page">{n}</b>
          ) : (
            <Link href={qs(base, { ...params, page: n })}>{n}</Link>
          )}
        </span>
      ))}
      {page < pages ? (
        <Link href={qs(base, { ...params, page: page + 1 })} rel="next">
          Sau →
        </Link>
      ) : (
        <span className="off">Sau →</span>
      )}
    </nav>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="empty">
      <Turtle clan="tu" size={90} mood="dizzy" />
      <div>{children}</div>
    </div>
  );
}
