'use client';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { PhotoGrid } from './client';
import { photos, streak, useSubs, type Photo } from './subs';

export default function Submissions() {
  const s = useSubs();
  const [all, setAll] = useState<Photo[] | null>(null);
  const [err, setErr] = useState('');
  const version = s ? Object.values(s.items).reduce((n, r) => n + r.at + r.n, 0) : 0;
  useEffect(() => {
    photos().then(setAll, (e: Error) => setErr(e.message));
  }, [version]);

  if (!s || (!all && !err)) return <div className="panel dark">Đang tải…</div>;
  const list = Object.values(s.items).sort((a, b) => b.at - a.at);
  const shots = list.reduce((n, r) => n + r.n, 0);
  const byPid = new Map<string, Photo[]>();
  for (const p of all ?? []) (byPid.get(p.pid) ?? byPid.set(p.pid, []).get(p.pid)!).push(p);

  return (
    <>
      <div className="stats three">
        <div className="stat">
          <b>{list.length}</b>
          <span>bài đã nộp</span>
        </div>
        <div className="stat">
          <b>{shots}</b>
          <span>ảnh</span>
        </div>
        <div className="stat">
          <b>{streak(s.days)}</b>
          <span>ngày liên tiếp</span>
        </div>
      </div>
      {err ? <p className="panel dark">{err}</p> : null}

      {list.length ? (
        <ol className="subs">
          {list.map((r) => (
            <li key={r.pid} className="panel dark">
              <div className="subs-head">
                <Link href={`/bai/${r.pid}`}>
                  <b>{r.label}</b> <span className="muted">— {r.title}</span>
                </Link>
                <span className="small muted">{new Date(r.at).toLocaleDateString('vi-VN')}</span>
              </div>
              <PhotoGrid list={byPid.get(r.pid) ?? []} />
            </li>
          ))}
        </ol>
      ) : (
        <p className="panel dark">
          Chưa nộp bài nào. Mở một <Link href="/luyen">bài toán</Link>, làm ra giấy rồi bấm <b>Chụp ảnh bài làm</b>.
        </p>
      )}
      <p className="muted small">Không cần đăng nhập: bài nộp gắn với trình duyệt trên máy này.</p>
    </>
  );
}
