import "server-only";
import { cacheLife, cacheTag } from "next/cache";
import { createClient } from "@supabase/supabase-js";
import type { SiteMedia } from "@/lib/media";

export type PublicReview = {
  id: string;
  customer_name: string;
  area: string | null;
  rating: number;
  body: string;
  created_at: string;
  reply: string | null;
};

export type GalleryItem = { id: string; title: string; image_url: string; before_url: string | null; tags: string[] };

function anonClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return null;
  return createClient(url, key, { auth: { persistSession: false } });
}

/** `preview` is true when Supabase is not connected yet and sample content is shown. */
export async function getPublishedReviews(): Promise<{ reviews: PublicReview[]; preview: boolean }> {
  "use cache";
  cacheLife("hours");
  cacheTag("reviews");

  const db = anonClient();
  if (!db) return { reviews: sampleReviews, preview: true };
  const { data } = await db
    .from("reviews")
    .select("id, customer_name, area, rating, body, created_at, reply")
    .eq("status", "published")
    .order("featured", { ascending: false })
    .order("created_at", { ascending: false })
    .limit(60);
  return { reviews: data ?? [], preview: false };
}

export async function getGallery(): Promise<{ items: GalleryItem[]; preview: boolean }> {
  "use cache";
  cacheLife("hours");
  cacheTag("gallery");

  const db = anonClient();
  if (!db) return { items: [], preview: true };
  const { data } = await db
    .from("gallery_items")
    .select("id, title, image_url, before_url, tags")
    .eq("consent_verified", true)
    .order("featured", { ascending: false })
    .order("created_at", { ascending: false })
    .limit(48);
  return { items: data ?? [], preview: false };
}

/** Photos uploaded in Admin → Site media, keyed by slot (see lib/media.ts). */
export async function getSiteMedia(): Promise<SiteMedia> {
  "use cache";
  cacheLife("hours");
  cacheTag("media");

  const db = anonClient();
  if (!db) return {};
  const { data } = await db.from("site_media").select("key, url, alt");
  return Object.fromEntries((data ?? []).map((m) => [m.key, { url: m.url, alt: m.alt }]));
}

export type Design = {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  occasion: string;
  price_from: number;
  image_url: string | null;
  images: string[];
  tags: string[];
  options: Record<string, string>;
  garment: string | null;
};

export async function getDesigns(): Promise<Design[]> {
  "use cache";
  cacheLife("hours");
  cacheTag("designs");

  const db = anonClient();
  if (!db) return sampleDesigns;
  const { data } = await db
    .from("designs")
    .select("id, slug, title, description, occasion, price_from, image_url, images, tags, options, garment:garment_types(slug)")
    .eq("is_active", true)
    .order("featured", { ascending: false })
    .order("sort")
    .order("created_at", { ascending: false });
  return (data ?? []).map((d) => ({ ...d, garment: (d.garment as unknown as { slug: string } | null)?.slug ?? null }));
}

// Layout preview only (no database): titles describe the cut, photos come later.
const sampleDesigns: Design[] = [
  ["Angrakha lawn kurta", "everyday", "kurti", 1650, { neckline: "v-neck", sleeves: "three-quarter", daman: "curved" }],
  ["Straight shirt with lace daman", "everyday", "designer", 3150, { neckline: "round", sleeves: "full", daman: "straight" }],
  ["Chiffon party wear with lining", "party", "party", 5250, { neckline: "sweetheart", sleeves: "bell", daman: "curved" }],
  ["Organza formal, band collar", "formal", "party", 5100, { neckline: "band-collar", sleeves: "full", daman: "straight" }],
  ["Flared maxi with kalis", "formal", "maxi", 6100, { neckline: "boat", sleeves: "puff", daman: "tulip" }],
  ["Eid co-ord with tulip shalwar", "eid", "designer", 3300, { neckline: "keyhole", sleeves: "three-quarter", trouser: "tulip" }],
  ["Jamawar winter shirt", "everyday", "designer", 3000, { neckline: "band-collar", sleeves: "full", daman: "asymmetric" }],
  ["Bridal lehenga — consultation", "bridal", "bridal", 15000, {}],
].map(([title, occasion, garment, price, options], i) => ({
  id: `d${i}`,
  slug: String(title).toLowerCase().replace(/[^a-z0-9]+/g, "-"),
  title: String(title),
  description: null,
  occasion: String(occasion),
  price_from: Number(price),
  image_url: null,
  images: [],
  tags: [],
  options: options as Record<string, string>,
  garment: String(garment),
}));

// Shown only in preview mode (no database connected) so the layout can be reviewed.
// Never publish these as real customer reviews.
const sampleReviews: PublicReview[] = [
  {
    id: "s1",
    customer_name: "Sample customer",
    area: "Gulberg",
    rating: 5,
    body: "Preview text — a verified customer review will appear here once orders are delivered.",
    created_at: "2026-11-01",
    reply: null,
  },
  {
    id: "s2",
    customer_name: "Sample customer",
    area: "DHA",
    rating: 5,
    body: "Preview text — reviews can only be written by customers whose order has been delivered.",
    created_at: "2026-11-01",
    reply: null,
  },
  {
    id: "s3",
    customer_name: "Sample customer",
    area: "Cantt",
    rating: 4,
    body: "Preview text — photo reviews, fit and on-time ratings show here.",
    created_at: "2026-11-01",
    reply: null,
  },
];
