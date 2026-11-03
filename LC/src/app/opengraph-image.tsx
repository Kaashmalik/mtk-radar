import { ogCard, ogSize } from "@/lib/og-card";

export const alt = "Laraib Creative — premium ladies suit stitching in Lahore with doorstep pickup";
export const size = ogSize;
export const contentType = "image/png";

export default function OpengraphImage() {
  return ogCard({ eyebrow: "Ladies tailoring house · Lahore", title: "Couture stitching, collected from your door." });
}
