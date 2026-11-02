import { ImageResponse } from 'next/og';

export const BRAND_BG = '#031f2b';

/**
 * The MTK Codex "</>" mark as an image at any size.
 * - standard: rounded tile with transparent corners (favicons, apple-touch)
 * - maskable: full-bleed square, glyph inside the 80% safe zone (Android adaptive icons)
 * - tile: flat glyph on the brand colour (Windows tiles)
 */
export function brandIcon(size: number, variant: 'standard' | 'maskable' | 'tile' = 'standard') {
  const full = variant !== 'standard';
  // Glyph scale: maskable keeps the mark well inside the safe zone.
  const glyph = variant === 'maskable' ? 0.62 : variant === 'tile' ? 0.7 : 1;
  const radius = full ? 0 : 11;
  const stroke = size <= 32 ? 3.6 : 3; // a touch bolder so tiny favicons stay legible

  return new ImageResponse(
    (
      <div style={{ width: size, height: size, display: 'flex' }}>
        <svg width={size} height={size} viewBox="0 0 40 40">
          <defs>
            <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#62d84e" />
              <stop offset="0.55" stopColor="#14a89a" />
              <stop offset="1" stopColor="#0b4f6c" />
            </linearGradient>
          </defs>
          <rect width="40" height="40" rx={radius} fill={variant === 'tile' ? BRAND_BG : 'url(#g)'} />
          <g transform={`translate(${20 - 20 * glyph} ${20 - 20 * glyph}) scale(${glyph})`}>
            <path d="M14 13 L8 20 L14 27" stroke="#fff" strokeWidth={stroke} fill="none" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M26 13 L32 20 L26 27" stroke="#fff" strokeWidth={stroke} fill="none" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M22.5 11 L17.5 29" stroke={variant === 'tile' ? '#62d84e' : '#fff'} strokeWidth={stroke} strokeLinecap="round" opacity="0.9" />
          </g>
        </svg>
      </div>
    ),
    { width: size, height: size },
  );
}

/** Packs PNG images into a single .ico (PNG-in-ICO, supported by all modern browsers). */
export function packIco(pngs: { size: number; data: Uint8Array }[]) {
  const header = 6;
  const entry = 16;
  let offset = header + entry * pngs.length;
  const total = offset + pngs.reduce((n, p) => n + p.data.length, 0);
  const buf = new Uint8Array(total);
  const view = new DataView(buf.buffer);
  view.setUint16(0, 0, true); // reserved
  view.setUint16(2, 1, true); // type: icon
  view.setUint16(4, pngs.length, true);
  pngs.forEach((p, i) => {
    const o = header + i * entry;
    view.setUint8(o, p.size >= 256 ? 0 : p.size); // width (0 = 256)
    view.setUint8(o + 1, p.size >= 256 ? 0 : p.size); // height
    view.setUint8(o + 2, 0); // palette
    view.setUint8(o + 3, 0); // reserved
    view.setUint16(o + 4, 1, true); // colour planes
    view.setUint16(o + 6, 32, true); // bits per pixel
    view.setUint32(o + 8, p.data.length, true);
    view.setUint32(o + 12, offset, true);
    buf.set(p.data, offset);
    offset += p.data.length;
  });
  return buf;
}
