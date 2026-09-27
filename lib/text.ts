export { snippet } from './md';

export const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? '';
export const num = (v: string | string[] | undefined) => {
  const n = parseInt(one(v), 10);
  return Number.isFinite(n) ? n : undefined;
};
export const plain = (s: string, max = 150) => {
  const t = s.replace(/\$\$?([^$]+)\$\$?/g, '$1').replace(/\\[a-zA-Z]+/g, '').replace(/[{}*#]/g, '').replace(/\s+/g, ' ').trim();
  return t.length > max ? t.slice(0, max - 1) + '…' : t;
};
