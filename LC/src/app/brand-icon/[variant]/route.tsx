import { ImageResponse } from "next/og";
import { Monogram } from "@/lib/brand-art";

// PNG icons at stable URLs for the web manifest, Google's search favicon (48px multiples)
// and the installable rider app. `maskable` keeps the mark inside Android's safe zone.
const variants = {
  "48": { size: 48, padding: 0.16, rounded: true },
  "96": { size: 96, padding: 0.16, rounded: true },
  "192": { size: 192, padding: 0.18, rounded: true },
  "512": { size: 512, padding: 0.18, rounded: true },
  "maskable-512": { size: 512, padding: 0.28, rounded: false },
} as const;

export function generateStaticParams() {
  return Object.keys(variants).map((variant) => ({ variant: `${variant}.png` }));
}

export async function GET(_: Request, { params }: RouteContext<"/brand-icon/[variant]">) {
  const { variant } = await params;
  const v = variants[variant.replace(/\.png$/, "") as keyof typeof variants];
  if (!v) return new Response("Not found", { status: 404 });
  return new ImageResponse(<Monogram size={v.size} padding={v.padding} rounded={v.rounded} />, {
    width: v.size,
    height: v.size,
    headers: { "Cache-Control": "public, max-age=31536000, immutable" },
  });
}
