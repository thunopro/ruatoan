'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Burst } from './art';
import { addPhotos, photos, photoUrl, removePhoto, useSubs, type Photo, type SubRec } from './subs';

const LINKS = [
  { href: '/luyen', label: 'Luyện bài' },
  { href: '/de', label: 'Đề thi' },
  { href: '/chuyen-de', label: 'Chuyên đề' },
  { href: '/sach', label: 'Sách' },
  { href: '/bai-nop', label: 'Bài nộp' },
];

export function Nav() {
  const path = usePathname();
  const s = useSubs();
  const n = s ? Object.keys(s.items).length : 0;
  return (
    <nav className="nav" aria-label="Điều hướng chính">
      {LINKS.map((l) => {
        const on = path.startsWith(l.href) || (l.href === '/luyen' && path.startsWith('/bai/')) || (l.href === '/chuyen-de' && path.startsWith('/ly-thuyet'));
        return (
          <Link key={l.href} href={l.href} className={on ? 'on' : undefined} aria-current={on ? 'page' : undefined}>
            {l.label}
            {l.href === '/bai-nop' && n ? <span className="nav-count">{n}</span> : null}
          </Link>
        );
      })}
    </nav>
  );
}

function Thumb({ p, onOpen, onDelete }: { p: Photo; onOpen: (url: string) => void; onDelete?: () => void }) {
  const url = photoUrl(p);
  return (
    <span className="thumb">
      <button type="button" className="thumb-img" onClick={() => onOpen(url)} aria-label="Xem ảnh lớn">
        <img src={url} alt="Ảnh bài làm" loading="lazy" />
      </button>
      {onDelete ? (
        <button type="button" className="thumb-del" onClick={onDelete} aria-label="Xóa ảnh">
          ×
        </button>
      ) : null}
    </span>
  );
}

export function PhotoGrid({ pid, editable, version = 0, list: given }: { pid?: string; editable?: boolean; version?: number; list?: Photo[] }) {
  const [own, setList] = useState<Photo[] | null>(null);
  const [big, setBig] = useState('');
  const load = useCallback(() => {
    if (!given) photos(pid).then(setList, () => setList([]));
  }, [pid, given]);
  useEffect(load, [load, version]);
  const list = given ?? own;
  if (!list?.length) return null;
  return (
    <>
      <div className="thumbs">
        {list.map((p) => (
          <Thumb
            key={p.id}
            p={p}
            onOpen={setBig}
            onDelete={
              editable
                ? () => {
                    if (confirm('Xóa ảnh này?')) removePhoto(p).then(load, (e: Error) => alert(e.message));
                  }
                : undefined
            }
          />
        ))}
      </div>
      {big ? (
        <div className="lightbox" role="dialog" aria-label="Ảnh bài làm" onClick={() => setBig('')}>
          <img src={big} alt="Ảnh bài làm" />
          <button type="button" className="btn sm" onClick={() => setBig('')}>
            Đóng
          </button>
        </div>
      ) : null}
    </>
  );
}

export function SubmitBox({ rec }: { rec: Omit<SubRec, 'at' | 'n'> }) {
  const s = useSubs();
  const done = s?.items[rec.pid];
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [boom, setBoom] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!boom) return;
    const t = setTimeout(() => setBoom(0), 1600);
    return () => clearTimeout(t);
  }, [boom]);

  return (
    <section className={`submit${done ? ' done' : ''}`} aria-labelledby="submit-title">
      <div className="submit-head">
        <div>
          <h2 id="submit-title" className="submit-title">
            {done ? 'Đã nộp bài' : 'Nộp bài'}
          </h2>
          <p className="small submit-sub">
            {done ? `${done.n} ảnh · ${new Date(done.at).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' })}` : 'Làm ra giấy rồi chụp ảnh bài làm.'}
          </p>
        </div>
        <label className={`btn big${busy || !s ? ' is-off' : ''}`}>
          {busy ? 'Đang lưu…' : done ? 'Thêm ảnh' : 'Chụp ảnh bài làm'}
          <input
            ref={input}
            type="file"
            accept="image/*"
            multiple
            hidden
            disabled={busy || !s}
            onChange={async (e) => {
              const files = [...(e.currentTarget.files ?? [])];
              e.currentTarget.value = '';
              if (!files.length) return;
              setBusy(true);
              setErr('');
              try {
                if (await addPhotos(rec, files)) setBoom(Date.now());
                else setErr('File không phải ảnh.');
              } catch (e) {
                setErr((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          />
        </label>
      </div>
      {err ? <p className="submit-err">{err}</p> : null}
      <PhotoGrid pid={rec.pid} editable version={done ? done.at + done.n : 0} />
      {boom ? (
        <div className="boom" key={boom} aria-live="assertive">
          <Burst text="ĐÃ NỘP!" className="boom-burst" />
        </div>
      ) : null}
    </section>
  );
}

/** Adds .is-done to [data-pid] cards on the page. Give it a key that changes with the list. */
export function DoneMarks() {
  const s = useSubs();
  useEffect(() => {
    if (!s) return;
    document.querySelectorAll<HTMLElement>('[data-pid]').forEach((el) => el.classList.toggle('is-done', !!s.items[el.dataset.pid!]));
  }, [s]);
  return null;
}

export function PrintButton() {
  return (
    <button className="btn ghost sm noprint" onClick={() => window.print()}>
      In đề
    </button>
  );
}
