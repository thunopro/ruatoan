export type TopicId = 'so-hoc' | 'dai-so' | 'bat-dang-thuc' | 'hinh-hoc' | 'to-hop';
export type ClanId = 'lam' | 'xich' | 'tu' | 'cam';
export type Kind = 'hsg' | 'chuyen' | 'tapchi' | 'chuyende' | 'olympic';

/** Mascot colour families (art only). */
export const CLANS: Record<ClanId, { mask: string; deep: string }> = {
  lam: { mask: '#2f8cff', deep: '#0b3d91' },
  xich: { mask: '#ff3b3b', deep: '#8f0d16' },
  tu: { mask: '#a15bff', deep: '#4a1a99' },
  cam: { mask: '#ff8a1f', deep: '#9a4300' },
};

export type Topic = { id: TopicId; name: string; clan: ClanId; color: string; ink: string; icon: string; desc: string };

export const TOPICS: Topic[] = [
  { id: 'so-hoc', name: 'Số học', clan: 'cam', color: '#ff8a1f', ink: '#5a2800', icon: '#', desc: 'Chia hết, đồng dư, số nguyên tố, số chính phương, nghiệm nguyên.' },
  { id: 'dai-so', name: 'Đại số', clan: 'tu', color: '#9b5cff', ink: '#35107a', icon: 'x²', desc: 'Biến đổi, căn thức, đa thức, phương trình và hệ phương trình.' },
  { id: 'bat-dang-thuc', name: 'Bất đẳng thức', clan: 'xich', color: '#ff3b3b', ink: '#6b0710', icon: '≥', desc: 'AM-GM, Cauchy–Schwarz, tìm giá trị lớn nhất, nhỏ nhất.' },
  { id: 'hinh-hoc', name: 'Hình học', clan: 'lam', color: '#2f8cff', ink: '#062a66', icon: '△', desc: 'Tam giác, đường tròn, tứ giác nội tiếp, quỹ tích.' },
  { id: 'to-hop', name: 'Tổ hợp', clan: 'cam', color: '#ff6a3d', ink: '#5c1a04', icon: 'n!', desc: 'Dirichlet, bất biến, cực hạn, đếm, trò chơi, tô màu.' },
];

export const TOPIC: Record<string, Topic> = Object.fromEntries(TOPICS.map((t) => [t.id, t]));
export const isTopic = (s: unknown): s is TopicId => typeof s === 'string' && s in TOPIC;

/** Content files may still use the older, finer topic ids. */
const ALIAS: Record<string, TopicId> = { 'nghiem-nguyen': 'so-hoc', 'phuong-trinh': 'dai-so' };
export const toTopic = (s: unknown): TopicId | undefined => (isTopic(s) ? s : typeof s === 'string' ? ALIAS[s] : undefined);

export const KINDS: Record<Kind, { name: string; long: string; stamp: string }> = {
  hsg: { name: 'HSG', long: 'Đề thi học sinh giỏi', stamp: 'HSG' },
  chuyen: { name: 'Vào 10', long: 'Đề thi vào 10 chuyên', stamp: 'VÀO 10' },
  tapchi: { name: 'Tạp chí', long: 'Bài toán trên tạp chí', stamp: 'TẠP CHÍ' },
  chuyende: { name: 'Chuyên đề', long: 'Bài tập chuyên đề', stamp: 'CHUYÊN ĐỀ' },
  olympic: { name: 'Olympic', long: 'Đề Olympic', stamp: 'OLYMPIC' },
};
export const isKind = (s: unknown): s is Kind => typeof s === 'string' && s in KINDS;
export const gradeName = (g: number) => (g === 10 ? 'Vào 10' : `Lớp ${g}`);

export const STAGES = [
  { stage: 1, name: 'Nền tảng', desc: 'Bắt đầu từ lớp 6' },
  { stage: 2, name: 'Nâng cao', desc: 'HSG, vào 10 chuyên' },
  { stage: 3, name: 'Chuyên sâu', desc: 'Olympic' },
] as const;
export const LANG_NAME = { vi: '', en: 'Tiếng Anh', ru: 'Tiếng Nga' } as const;
