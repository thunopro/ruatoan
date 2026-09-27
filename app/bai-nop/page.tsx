import type { Metadata } from 'next';
import { PageHead } from '../ui/bits';
import Submissions from '../ui/Submissions';

export const metadata: Metadata = { title: 'Bài nộp', description: 'Ảnh bài làm bạn đã nộp.' };

export default function BaiNop() {
  return (
    <>
      <PageHead title="Bài nộp" clan="cam" />
      <Submissions />
    </>
  );
}
