import type { Metadata } from 'next';
import Link from 'next/link';
import type { CSSProperties } from 'react';
import { docs, lessons, topicCount } from '@/lib/content';
import { TOPICS } from '@/lib/topics';
import { PageHead } from '../ui/bits';

export const metadata: Metadata = { title: 'Chuyên đề', description: 'Bài giảng, tài liệu PDF và bài tập toán nâng cao THCS theo 5 chuyên đề.' };

export default function ChuyenDe() {
  const ls = lessons();
  const ds = docs();
  return (
    <>
      <PageHead title="Chuyên đề" clan="lam" />
      <div className="tcards">
        {TOPICS.map((t) => (
          <Link key={t.id} href={`/chuyen-de/${t.id}`} className="tcard" style={{ '--t': t.color, '--ti': t.ink } as CSSProperties}>
            <b className="topic-icon" aria-hidden="true">
              {t.icon}
            </b>
            <h2>{t.name}</h2>
            <p className="small">{t.desc}</p>
            <p className="tcard-n">
              <span>{ls.filter((l) => l.topic === t.id).length} bài giảng</span>
              <span>{ds.filter((d) => d.topic === t.id).length} tài liệu</span>
              <span>{topicCount(t.id)} bài tập</span>
            </p>
          </Link>
        ))}
      </div>
    </>
  );
}
