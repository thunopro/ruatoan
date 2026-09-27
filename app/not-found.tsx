import Link from 'next/link';
import { Turtle } from './ui/art';

export const metadata = { title: 'Không tìm thấy trang' };

export default function NotFound() {
  return (
    <section className="nf">
      <div className="nf-art">
        <Turtle clan="tu" size={180} mood="dizzy" />
      </div>
      <div>
        <p className="kicker">Lỗi 404</p>
        <h1>Không tìm thấy trang</h1>
        <div className="row">
          <Link href="/" className="btn">
            Trang chủ
          </Link>
          <Link href="/luyen" className="btn ghost">
            Luyện bài
          </Link>
        </div>
      </div>
    </section>
  );
}
