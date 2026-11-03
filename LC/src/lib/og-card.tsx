import { ImageResponse } from "next/og";
import { BRAND_GOLD, BRAND_IVORY, BRAND_PLUM, Monogram } from "@/lib/brand-art";

export const ogSize = { width: 1200, height: 630 };

/** Branded 1200×630 share card used for WhatsApp, Facebook, X and Google Discover previews. */
export function ogCard({ eyebrow, title, footer = "laraibcreative.com · Garhi Shahu, Lahore" }: { eyebrow: string; title: string; footer?: string }) {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between", background: BRAND_PLUM, padding: 72, color: BRAND_IVORY }}>
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <Monogram size={84} padding={0.16} />
          <div style={{ display: "flex", flexDirection: "column" }}>
            <span style={{ fontSize: 40, letterSpacing: -1 }}>Laraib</span>
            <span style={{ fontSize: 16, letterSpacing: 8, color: BRAND_GOLD }}>CREATIVE</span>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", maxWidth: 980 }}>
          <span style={{ fontSize: 22, letterSpacing: 6, color: BRAND_GOLD, textTransform: "uppercase" }}>{eyebrow}</span>
          <span style={{ fontSize: title.length > 48 ? 58 : 72, lineHeight: 1.05, marginTop: 18, letterSpacing: -2 }}>{title}</span>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 22, color: "rgba(247,241,232,0.7)" }}>
          <span>{footer}</span>
          <div style={{ display: "flex", gap: 6 }}>
            {Array.from({ length: 24 }).map((_, i) => (
              <div key={i} style={{ width: 9, height: 2, background: BRAND_GOLD }} />
            ))}
          </div>
        </div>
      </div>
    ),
    ogSize,
  );
}
