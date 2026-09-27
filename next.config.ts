import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // Content is read from ./content with fs at request time (on-demand pages) — make sure it ships with the server bundle.
  outputFileTracingIncludes: { '/**': ['./content/**/*.json'] },
  outputFileTracingExcludes: { '/**': ['./.cache/**', './scripts/**', './.data/**'] },
  async redirects() {
    return [
      { source: '/bi-kip', destination: '/chuyen-de', permanent: true },
      { source: '/bi-kip/:id', destination: '/ly-thuyet/:id', permanent: true },
      { source: '/dojo', destination: '/bai-nop', permanent: true },
    ];
  },
};

export default nextConfig;
