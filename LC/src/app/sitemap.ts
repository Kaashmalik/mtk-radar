import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/seo";
import { areas } from "@/lib/content/areas";
import { articles } from "@/lib/content/journal";

const LAST_UPDATE = "2026-11-04";

export default function sitemap(): MetadataRoute.Sitemap {
  const page = (path: string, priority: number, changeFrequency: MetadataRoute.Sitemap[number]["changeFrequency"] = "monthly") => ({
    url: `${SITE_URL}${path}`,
    lastModified: LAST_UPDATE,
    changeFrequency,
    priority,
  });

  return [
    page("/", 1, "weekly"),
    page("/order", 0.9),
    page("/services", 0.9),
    page("/designs", 0.8, "weekly"),
    page("/pricing", 0.8),
    page("/how-it-works", 0.7),
    page("/gallery", 0.7, "weekly"),
    page("/reviews", 0.7, "weekly"),
    page("/size-guide", 0.6),
    page("/contact", 0.7),
    page("/about", 0.6),
    page("/journal", 0.6, "weekly"),
    page("/tailor", 0.7),
    ...areas.map((a) => page(`/tailor/${a.slug}`, 0.8)),
    ...articles.map((a) => ({ ...page(`/journal/${a.slug}`, 0.5), lastModified: a.published })),
    page("/privacy", 0.2, "yearly"),
    page("/terms", 0.2, "yearly"),
    page("/refund-policy", 0.3, "yearly"),
  ];
}
