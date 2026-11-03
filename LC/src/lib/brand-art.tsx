// Brand mark rendered by next/og (ImageResponse) for favicons, app icons and share images.

export const BRAND_PLUM = "#3b1f2b";
export const BRAND_GOLD = "#b08d57";
export const BRAND_IVORY = "#f7f1e8";

/** The monogram: an "L" drawn as a stitched gold thread ending at a needle. */
export function Monogram({ size, padding = 0.18, rounded = true }: { size: number; padding?: number; rounded?: boolean }) {
  const inner = size * (1 - padding * 2);
  return (
    <div
      style={{
        width: size,
        height: size,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: BRAND_PLUM,
        borderRadius: rounded ? size * 0.22 : 0,
      }}
    >
      <svg width={inner} height={inner} viewBox="0 0 40 40">
        <path d="M14 7v21c0 1.7 1.3 3 3 3h12" fill="none" stroke={BRAND_GOLD} strokeWidth="3" strokeLinecap="round" strokeDasharray="3.6 2.6" />
        <ellipse cx="28.5" cy="10.5" rx="2.2" ry="4.4" fill="none" stroke={BRAND_IVORY} strokeWidth="2.2" />
        <path d="M28.5 15v9" stroke={BRAND_IVORY} strokeWidth="2.2" strokeLinecap="round" />
      </svg>
    </div>
  );
}
