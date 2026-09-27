import type { Metadata, Viewport } from 'next';
import { Be_Vietnam_Pro, Bungee } from 'next/font/google';
import Link from 'next/link';
import 'katex/dist/katex.min.css';
import './globals.css';
import { Turtle } from './ui/art';
import { Nav } from './ui/client';

const body = Be_Vietnam_Pro({ subsets: ['vietnamese', 'latin'], weight: ['400', '500', '700', '800'], variable: '--font-main', display: 'swap' });
const display = Bungee({ subsets: ['vietnamese', 'latin'], weight: '400', variable: '--font-display', display: 'swap' });

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || 'https://ruatoan.vercel.app'),
  title: { default: 'Rùa Toán — Toán nâng cao THCS', template: '%s · Rùa Toán' },
  description: 'Đề HSG lớp 6–9, đề vào 10 chuyên và tài liệu toán nâng cao THCS theo chuyên đề.',
  openGraph: { siteName: 'Rùa Toán', locale: 'vi_VN', type: 'website' },
};
export const viewport: Viewport = { themeColor: '#07140c', width: 'device-width', initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi" className={`${body.variable} ${display.variable}`}>
      <body>
        <a href="#main" className="skip">
          Bỏ qua điều hướng
        </a>
        <header className="top">
          <div className="top-in">
            <Link href="/" className="brand" aria-label="Rùa Toán — trang chủ">
              <Turtle clan="lam" size={40} className="brand-art" />
              <span className="brand-name">
                Rùa <b>Toán</b>
              </span>
            </Link>
            <Nav />
          </div>
          <svg className="ooze-drip" viewBox="0 0 1200 28" preserveAspectRatio="none" aria-hidden="true">
            <path d="M0 0H1200V8C1170 8 1165 22 1150 22S1132 8 1100 8 1010 12 990 12 975 26 960 26 944 12 920 10 760 8 740 8 728 18 716 18 703 8 690 8 520 8 500 10 488 24 474 24 460 10 440 9 300 8 280 8 270 16 260 16 250 8 238 8 130 8 110 10 100 21 88 21 76 10 60 9L0 8Z" />
          </svg>
        </header>
        <main id="main">{children}</main>
        <footer className="foot">
          <div className="foot-in">
            <p className="small">
              <b>Rùa Toán</b> · Đề bài ghi rõ nguồn ở từng đề. Tài liệu và sách dẫn link về trang gốc.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
