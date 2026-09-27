import { CLANS, type ClanId } from '@/lib/topics';

const INK = '#0d1a0f';

/** Original mascot: chibi ninja turtle with a clan-coloured eye mask. */
export function Turtle({ clan = 'lam', size = 120, className, mood = 'happy', title }: { clan?: ClanId; size?: number; className?: string; mood?: 'happy' | 'focus' | 'dizzy'; title?: string }) {
  const mask = CLANS[clan].mask;
  return (
    <svg viewBox="0 0 200 210" width={size} height={size * 1.05} className={className} role={title ? 'img' : undefined} aria-hidden={title ? undefined : true} aria-label={title}>
      <ellipse cx="100" cy="201" rx="64" ry="8" fill="rgba(0,0,0,.35)" />
      {/* bandana tails */}
      <path d="M150 64C170 48 190 52 199 66C185 67 172 72 157 82Z" fill={mask} stroke={INK} strokeWidth="4" strokeLinejoin="round" />
      <path d="M152 78C176 84 190 100 188 124C177 110 163 100 147 93Z" fill={mask} stroke={INK} strokeWidth="4" strokeLinejoin="round" />
      {/* shell rim */}
      <ellipse cx="100" cy="152" rx="63" ry="50" fill="#7b5a2c" stroke={INK} strokeWidth="5" />
      <path d="M44 150Q40 124 56 108M156 150Q160 124 144 108" stroke="#a57a3d" strokeWidth="5" fill="none" strokeLinecap="round" />
      {/* arms */}
      <path d="M52 128C32 136 26 158 34 176" stroke={INK} strokeWidth="21" fill="none" strokeLinecap="round" />
      <path d="M52 128C32 136 26 158 34 176" stroke="#5cc85a" strokeWidth="12" fill="none" strokeLinecap="round" />
      <path d="M148 128C168 136 174 158 166 176" stroke={INK} strokeWidth="21" fill="none" strokeLinecap="round" />
      <path d="M148 128C168 136 174 158 166 176" stroke="#5cc85a" strokeWidth="12" fill="none" strokeLinecap="round" />
      {/* feet */}
      <ellipse cx="74" cy="192" rx="21" ry="12" fill="#5cc85a" stroke={INK} strokeWidth="4.5" />
      <ellipse cx="126" cy="192" rx="21" ry="12" fill="#5cc85a" stroke={INK} strokeWidth="4.5" />
      {/* plastron */}
      <path d="M58 118Q100 104 142 118Q152 162 128 190Q100 200 72 190Q48 162 58 118Z" fill="#f4d27a" stroke={INK} strokeWidth="5" strokeLinejoin="round" />
      <path d="M60 142Q100 152 140 142M62 166Q100 176 138 166M100 112V194" stroke="#c39a45" strokeWidth="4" fill="none" strokeLinecap="round" />
      {/* belt */}
      <path d="M55 132Q100 146 145 132L146 146Q100 160 54 146Z" fill={mask} stroke={INK} strokeWidth="4" strokeLinejoin="round" />
      <circle cx="100" cy="148" r="8" fill={mask} stroke={INK} strokeWidth="4" />
      {/* head */}
      <ellipse cx="100" cy="72" rx="60" ry="52" fill="#5cc85a" />
      <path d="M46 92Q100 138 154 92Q150 118 100 124Q52 118 46 92Z" fill="#46a646" />
      <path d="M40 58Q100 42 160 58L160 91Q100 79 40 91Z" fill={mask} />
      <path d="M40 58Q100 42 160 58" stroke="rgba(255,255,255,.35)" strokeWidth="3" fill="none" />
      {mood === 'dizzy' ? (
        <g stroke={INK} strokeWidth="5" strokeLinecap="round">
          <path d="M68 64l20 18M88 64l-20 18M112 64l20 18M132 64l-20 18" />
        </g>
      ) : (
        <g>
          <path d={mood === 'focus' ? 'M64 70Q78 60 92 68Q88 86 74 84Q64 80 64 70Z' : 'M65 73a13 14 0 1 0 26 0a13 14 0 1 0-26 0Z'} fill="#fff" stroke={INK} strokeWidth="3.5" />
          <path d={mood === 'focus' ? 'M136 70Q122 60 108 68Q112 86 126 84Q136 80 136 70Z' : 'M109 73a13 14 0 1 0 26 0a13 14 0 1 0-26 0Z'} fill="#fff" stroke={INK} strokeWidth="3.5" />
          <circle cx="81" cy="75" r="6.5" fill={INK} />
          <circle cx="119" cy="75" r="6.5" fill={INK} />
          <circle cx="83.5" cy="72" r="2.2" fill="#fff" />
          <circle cx="121.5" cy="72" r="2.2" fill="#fff" />
        </g>
      )}
      <ellipse cx="100" cy="72" rx="60" ry="52" fill="none" stroke={INK} strokeWidth="5" />
      <ellipse cx="72" cy="36" rx="15" ry="7" fill="#fff" opacity=".28" transform="rotate(-22 72 36)" />
      <circle cx="62" cy="100" r="7" fill="#ff8fa3" opacity=".55" />
      <circle cx="138" cy="100" r="7" fill="#ff8fa3" opacity=".55" />
      {mood === 'dizzy' ? (
        <path d="M86 106Q93 100 100 106Q107 112 114 106" stroke={INK} strokeWidth="4" fill="none" strokeLinecap="round" />
      ) : (
        <path d="M84 100Q100 116 116 100" stroke={INK} strokeWidth="4.5" fill={mood === 'happy' ? '#7a1f2b' : 'none'} strokeLinecap="round" strokeLinejoin="round" />
      )}
    </svg>
  );
}

/** Comic starburst sticker. */
export function Burst({ text, color = '#ffd23f', className }: { text: string; color?: string; className?: string }) {
  const pts = Array.from({ length: 28 }, (_, i) => {
    const r = i % 2 ? 58 : 94;
    const a = (i / 28) * Math.PI * 2;
    return `${(100 + r * Math.cos(a)).toFixed(1)},${(100 + r * Math.sin(a) * 0.82).toFixed(1)}`;
  }).join(' ');
  return (
    <svg viewBox="0 0 200 200" className={className} aria-hidden="true">
      <polygon points={pts} fill={INK} transform="translate(6 6)" />
      <polygon points={pts} fill={color} stroke={INK} strokeWidth="5" strokeLinejoin="round" />
      <text x="100" y="114" textAnchor="middle" fontFamily="var(--font-display)" fontSize="40" fill="#fff" stroke={INK} strokeWidth="7" paintOrder="stroke" transform="rotate(-8 100 100)">
        {text}
      </text>
    </svg>
  );
}
