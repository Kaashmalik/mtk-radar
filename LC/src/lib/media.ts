// Every photo slot on the public site. Photos are uploaded from Admin → Site media
// (stored in Cloudinary, URL saved in `site_media`); until then a neutral placeholder shows.

export type MediaSlot = { key: string; label: string; group: string; ratio: string; hint: string };

export const mediaSlots: MediaSlot[] = [
  { key: "hero.main", label: "Hero — main photo", group: "Home", ratio: "4/5", hint: "Model in a finished suit, portrait, warm light" },
  { key: "hero.detail", label: "Hero — detail photo", group: "Home", ratio: "3/4", hint: "Close-up of neckline embroidery or piping" },
  { key: "home.workshop", label: "Workshop / craft", group: "Home", ratio: "16/10", hint: "Master tailor cutting fabric at Garhi Shahu" },
  { key: "home.rider", label: "Laraib rider", group: "Home", ratio: "4/3", hint: "Rider in uniform with the sealed fabric bag" },
  { key: "service.simple", label: "Simple suit", group: "Services", ratio: "4/3", hint: "" },
  { key: "service.designer", label: "Designer suit", group: "Services", ratio: "4/3", hint: "" },
  { key: "service.party", label: "Party / fancy wear", group: "Services", ratio: "4/3", hint: "" },
  { key: "service.kurti", label: "Kurti / short shirt", group: "Services", ratio: "4/3", hint: "" },
  { key: "service.maxi", label: "Maxi / frock", group: "Services", ratio: "4/3", hint: "" },
  { key: "service.bridal", label: "Bridal & formal", group: "Services", ratio: "4/3", hint: "" },
  { key: "about.studio", label: "Studio front", group: "Contact", ratio: "16/10", hint: "Garhi Shahu studio entrance / signage" },
  { key: "og.default", label: "Social share image", group: "SEO", ratio: "1200/630", hint: "Shown when the site is shared on WhatsApp / Facebook" },
];

export type SiteMedia = Record<string, { url: string; alt: string }>;

/** Inserts Cloudinary delivery transformations (format, quality, width) into an upload URL. */
export function cloudinaryUrl(src: string, width: number, quality: "auto" | "auto:good" = "auto") {
  if (!src.includes("res.cloudinary.com") || !src.includes("/upload/")) return src;
  return src.replace("/upload/", `/upload/f_auto,q_${quality},c_limit,w_${width}/`);
}
