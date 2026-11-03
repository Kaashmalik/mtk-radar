import { articles } from "@/lib/content/journal";
import { ogCard, ogSize } from "@/lib/og-card";

export const alt = "Laraib Creative Style Journal";
export const size = ogSize;
export const contentType = "image/png";

export function generateStaticParams() {
  return articles.map((a) => ({ slug: a.slug }));
}

export default async function Image({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const a = articles.find((x) => x.slug === slug);
  return ogCard({ eyebrow: `Style Journal · ${a?.category ?? ""}`, title: a?.title ?? "Style Journal" });
}
