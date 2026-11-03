import { ImageResponse } from "next/og";
import { Monogram } from "@/lib/brand-art";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

// iOS adds its own rounded mask, so the square is drawn without corners.
export default function AppleIcon() {
  return new ImageResponse(<Monogram size={180} padding={0.2} rounded={false} />, size);
}
