'use client';
import { useSyncExternalStore } from 'react';

/**
 * Bài nộp = ảnh chụp bài làm, nén nhẹ trong trình duyệt rồi lưu vào database (/api/photos).
 * Không cần đăng nhập: mỗi máy có một mã thiết bị ngẫu nhiên. localStorage giữ bản tóm tắt để đánh dấu nhanh.
 */
export type SubRec = { pid: string; label: string; title: string; at: number; n: number };
export type Subs = { items: Record<string, SubRec>; days: string[] };
export type Photo = { id: string; pid: string; label: string; title: string; at: number };

const KEY = 'toan:subs:v2';
const DEVICE = 'toan:device';
const EVT = 'toan-subs';

// ---------- index (localStorage) ----------
const read = () => {
  try {
    return localStorage.getItem(KEY) ?? '';
  } catch {
    return '';
  }
};
let lastRaw: string | null = null;
let lastVal: Subs = { items: {}, days: [] };
const parse = (raw: string): Subs => {
  if (raw === lastRaw) return lastVal;
  lastRaw = raw;
  try {
    const d = JSON.parse(raw);
    lastVal = { items: d && typeof d.items === 'object' ? d.items : {}, days: Array.isArray(d?.days) ? d.days : [] };
  } catch {
    lastVal = { items: {}, days: [] };
  }
  return lastVal;
};
const write = (s: Subs) => {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {}
  window.dispatchEvent(new Event(EVT));
};

function subscribe(cb: () => void) {
  window.addEventListener(EVT, cb);
  window.addEventListener('storage', cb);
  return () => {
    window.removeEventListener(EVT, cb);
    window.removeEventListener('storage', cb);
  };
}

/** Returns null during SSR / before hydration. */
export function useSubs(): Subs | null {
  const raw = useSyncExternalStore(subscribe, read, () => null);
  return raw === null ? null : parse(raw);
}

export const today = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

export function streak(days: string[]) {
  const set = new Set(days);
  const d = new Date();
  if (!set.has(today(d))) d.setDate(d.getDate() - 1);
  let n = 0;
  while (set.has(today(d))) {
    n++;
    d.setDate(d.getDate() - 1);
  }
  return n;
}

// ---------- photos (server) ----------
function deviceId() {
  try {
    let id = localStorage.getItem(DEVICE);
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem(DEVICE, id);
    }
    return id;
  } catch {
    return '';
  }
}

async function api<T>(url: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(url, { ...init, headers: { ...init.headers, 'x-device': deviceId() } });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || 'Lỗi mạng, thử lại sau.');
  return d as T;
}

export const photoUrl = (p: Photo) => `/api/photos/${p.id}`;

/** Rebuild the local summary from a full photo list. */
function reindex(list: Photo[]) {
  const items: Record<string, SubRec> = {};
  const days = new Set(parse(read()).days);
  for (const p of list) {
    const r = (items[p.pid] ??= { pid: p.pid, label: p.label, title: p.title, at: 0, n: 0 });
    r.n++;
    r.at = Math.max(r.at, p.at);
    days.add(today(new Date(p.at)));
  }
  const next = { items, days: [...days].sort().slice(-400) };
  if (JSON.stringify(next) !== read()) write(next);
}

export async function photos(pid?: string): Promise<Photo[]> {
  const { photos } = await api<{ photos: Photo[] }>(pid ? `/api/photos?problem=${encodeURIComponent(pid)}` : '/api/photos');
  if (!pid) reindex(photos);
  return photos.sort((a, b) => a.at - b.at);
}

/**
 * Phone photos (4–12 MB) → grayscale, contrast-boosted WebP (JPEG fallback), long edge ≤ 1000 px.
 * Handwriting stays readable at ~30–80 KB.
 */
async function shrink(file: File): Promise<Blob> {
  const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' });
  let last: Blob | null = null;
  for (const [px, q] of [[1000, 0.4], [850, 0.35], [700, 0.3]] as const) {
    const k = Math.min(1, px / Math.max(bmp.width, bmp.height));
    const c = document.createElement('canvas');
    c.width = Math.round(bmp.width * k);
    c.height = Math.round(bmp.height * k);
    const ctx = c.getContext('2d')!;
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, c.width, c.height);
    ctx.filter = 'grayscale(1) contrast(1.25) brightness(1.05)';
    ctx.drawImage(bmp, 0, 0, c.width, c.height);
    let b = await new Promise<Blob | null>((ok) => c.toBlob(ok, 'image/webp', q));
    if (!b || b.type !== 'image/webp') b = await new Promise<Blob | null>((ok) => c.toBlob(ok, 'image/jpeg', q));
    if (b && b.size < 80_000) {
      bmp.close();
      return b;
    }
    if (b) last = b;
  }
  bmp.close();
  if (last && last.size < 150_000) return last;
  throw new Error('Ảnh quá lớn.');
}

export async function addPhotos(meta: Omit<SubRec, 'at' | 'n'>, files: File[]) {
  const imgs = files.filter((f) => f.type.startsWith('image/') || !f.type).slice(0, 6);
  if (!imgs.length) return 0;
  let blobs: Blob[];
  try {
    blobs = await Promise.all(imgs.map(shrink));
  } catch {
    throw new Error('Không đọc được ảnh này, thử chụp lại.');
  }
  const form = new FormData();
  form.set('problem', meta.pid);
  form.set('label', meta.label);
  form.set('title', meta.title);
  for (const b of blobs) form.append('images', b, b.type === 'image/webp' ? 'a.webp' : 'a.jpg');
  const { photos: added } = await api<{ photos: Photo[] }>('/api/photos', { method: 'POST', body: form });
  const cur = parse(read());
  const prev = cur.items[meta.pid];
  write({
    items: { ...cur.items, [meta.pid]: { ...meta, at: Date.now(), n: (prev?.n ?? 0) + added.length } },
    days: [...new Set([...cur.days, today()])].sort().slice(-400),
  });
  return added.length;
}

export async function removePhoto(p: Photo) {
  await api(`/api/photos/${p.id}`, { method: 'DELETE' });
  const cur = parse(read());
  const items = { ...cur.items };
  const r = items[p.pid];
  if (r && r.n > 1) items[p.pid] = { ...r, n: r.n - 1 };
  else delete items[p.pid];
  write({ items, days: cur.days });
}
