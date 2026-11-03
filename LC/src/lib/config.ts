// Business configuration. Values here are the public, rarely-changing defaults;
// the admin can override catalog/zone data in Supabase.

export const brand = {
  name: "Laraib Creative",
  domain: "laraibcreative.com",
  tagline: "Your fabric. Our craft. Perfect fit — on time.",
  phone: process.env.NEXT_PUBLIC_BUSINESS_PHONE ?? "+92 300 0000000",
  whatsapp: process.env.NEXT_PUBLIC_WHATSAPP_NUMBER ?? "923000000000",
  email: "hello@laraibcreative.com",
  address: "Allama Iqbal Road, near Pakistan Railways Headquarters, Garhi Shahu, Lahore",
  hours: "Mon – Sat · 11:00 am – 8:00 pm",
  mapsUrl: "https://maps.google.com/?q=Pakistan+Railways+Headquarters+Garhi+Shahu+Lahore",
  instagram: "https://instagram.com/laraibcreative",
  facebook: "https://facebook.com/laraibcreative",
  tiktok: "https://tiktok.com/@laraibcreative",
};

export function whatsappLink(message: string) {
  return `https://wa.me/${brand.whatsapp}?text=${encodeURIComponent(message)}`;
}

export type Garment = {
  slug: string;
  name: string;
  basePrice: number;
  days: number;
  blurb: string;
};

export const garments: Garment[] = [
  { slug: "simple", name: "Simple Suit", basePrice: 1800, days: 7, blurb: "Shirt, shalwar or trouser, dupatta edging." },
  { slug: "designer", name: "Designer Suit", basePrice: 2800, days: 8, blurb: "Piping, panels, buttons and lace placement." },
  { slug: "party", name: "Party / Fancy Wear", basePrice: 4500, days: 10, blurb: "Lining, cancan, finishing for evening wear." },
  { slug: "kurti", name: "Kurti / Short Shirt", basePrice: 1400, days: 6, blurb: "Everyday kurtis with clean, modern cuts." },
  { slug: "maxi", name: "Maxi / Frock", basePrice: 5500, days: 12, blurb: "Flared kalis, layered frocks, peshwas." },
  { slug: "bridal", name: "Bridal & Formal", basePrice: 15000, days: 21, blurb: "Lehenga, sharara, gharara — by consultation." },
];

export type OptionGroup = { key: string; label: string; options: { value: string; label: string; price: number }[] };

export const designOptions: OptionGroup[] = [
  {
    key: "neckline",
    label: "Neckline",
    options: [
      { value: "round", label: "Round", price: 0 },
      { value: "v-neck", label: "V-neck", price: 0 },
      { value: "boat", label: "Boat", price: 150 },
      { value: "sweetheart", label: "Sweetheart", price: 250 },
      { value: "band-collar", label: "Band collar", price: 200 },
      { value: "keyhole", label: "Keyhole", price: 200 },
    ],
  },
  {
    key: "sleeves",
    label: "Sleeves",
    options: [
      { value: "full", label: "Full", price: 0 },
      { value: "three-quarter", label: "¾ length", price: 0 },
      { value: "bell", label: "Bell", price: 250 },
      { value: "puff", label: "Puff", price: 300 },
      { value: "sleeveless", label: "Sleeveless", price: 0 },
    ],
  },
  {
    key: "daman",
    label: "Daman (hem)",
    options: [
      { value: "straight", label: "Straight", price: 0 },
      { value: "curved", label: "Curved", price: 150 },
      { value: "tulip", label: "Tulip", price: 250 },
      { value: "asymmetric", label: "Asymmetric", price: 300 },
    ],
  },
  {
    key: "trouser",
    label: "Bottom",
    options: [
      { value: "shalwar", label: "Shalwar", price: 0 },
      { value: "cigarette", label: "Cigarette pants", price: 0 },
      { value: "bell-bottom", label: "Bell bottom", price: 200 },
      { value: "tulip", label: "Tulip shalwar", price: 250 },
      { value: "palazzo", label: "Palazzo", price: 200 },
      { value: "culottes", label: "Culottes", price: 150 },
    ],
  },
];

export const addons = [
  { value: "lining", label: "Lining", price: 500 },
  { value: "piping", label: "Piping", price: 300 },
  { value: "lace", label: "Lace attachment", price: 350 },
  { value: "buttons", label: "Designer buttons / potli", price: 250 },
  { value: "pico", label: "Dupatta pico / hemming", price: 200 },
];

export const tiers = [
  { value: "standard", label: "Standard", days: "7–10 days", fee: 0 },
  { value: "priority", label: "Priority", days: "4–5 days", fee: 800 },
  { value: "express", label: "Express", days: "48 hours", fee: 1800 },
] as const;

export type Zone = { code: "A" | "B" | "C"; name: string; fee: number; freeAbove: number; areas: string[]; note: string };

export const zones: Zone[] = [
  {
    code: "A",
    name: "Core",
    fee: 150,
    freeAbove: 5000,
    areas: ["Garhi Shahu", "Shadman", "GOR", "Upper Mall", "Cantt", "Cavalry Ground", "Gulberg"],
    note: "Daily same-day slots",
  },
  {
    code: "B",
    name: "Prime",
    fee: 250,
    freeAbove: 8000,
    areas: ["DHA Phase 1–6", "Askari", "Model Town", "Garden Town", "Faisal Town", "Walton"],
    note: "Daily slots",
  },
  {
    code: "C",
    name: "Extended",
    fee: 400,
    freeAbove: 12000,
    areas: ["DHA Phase 7–9", "Johar Town", "Wapda Town", "Bahria Town", "Valencia", "Lake City"],
    note: "Fixed pickup days (Tue & Fri)",
  },
];

export const pickupSlots = ["11:00 am – 1:00 pm", "3:00 pm – 5:00 pm", "6:00 pm – 8:00 pm"];

export const measurementMethods = [
  { value: "home_visit", title: "Home measurement visit", desc: "A trained Laraib measurer visits you — female staff by default.", badge: "Most accurate" },
  { value: "sample_suit", title: "Send a stitched suit", desc: "Our rider collects a suit that fits you well. We copy it and return it.", badge: "Copy my fit" },
  { value: "standard_size", title: "Laraib standard size", desc: "Choose XS – 3XL from our chart, benchmarked against leading brands.", badge: null },
  { value: "brand_match", title: "“I wear M in …”", desc: "Tell us your size in the brand you usually buy. We match it.", badge: "Fastest" },
  { value: "self", title: "Measure yourself", desc: "Guided step-by-step with illustrations for each measurement.", badge: null },
  { value: "video_call", title: "Video-call measurement", desc: "10-minute WhatsApp video call — ideal outside Lahore.", badge: null },
] as const;

export type MeasurementMethod = (typeof measurementMethods)[number]["value"];

export const standardSizes = ["XS", "S", "M", "L", "XL", "XXL", "3XL"];

// Brand names are used only as text for size equivalence. Laraib Creative is not affiliated with them.
export const benchmarkBrands = ["Khaadi", "Sapphire", "Gul Ahmed", "Alkaram", "J.", "Limelight", "Generation", "Maria B", "Sana Safinaz"];

export const selfMeasureFields = [
  { key: "chest", label: "Chest", hint: "Around the fullest part of the bust" },
  { key: "waist", label: "Waist", hint: "Around the natural waistline" },
  { key: "hip", label: "Hip", hint: "Around the fullest part of the hips" },
  { key: "shoulder", label: "Shoulder", hint: "From shoulder tip to shoulder tip" },
  { key: "sleeve", label: "Sleeve length", hint: "Shoulder tip to wrist" },
  { key: "length", label: "Shirt length", hint: "Shoulder to desired hem" },
  { key: "trouser", label: "Trouser length", hint: "Waist to ankle" },
];

export type PaymentAccount = { type: string; label: string; title: string; number: string; bank?: string; iban?: string };

// Replace with your real accounts (or manage them in Supabase `payment_accounts`).
export const paymentAccounts: PaymentAccount[] = [
  {
    type: "bank",
    label: "Bank transfer",
    title: "Laraib Creative",
    bank: process.env.NEXT_PUBLIC_BANK_NAME ?? "Meezan Bank",
    number: process.env.NEXT_PUBLIC_BANK_ACCOUNT ?? "0000 0000 0000 00",
    iban: process.env.NEXT_PUBLIC_BANK_IBAN ?? "PK00 MEZN 0000 0000 0000 0000",
  },
  { type: "jazzcash", label: "JazzCash", title: "Laraib Creative", number: process.env.NEXT_PUBLIC_JAZZCASH ?? "0300 0000000" },
  { type: "easypaisa", label: "Easypaisa", title: "Laraib Creative", number: process.env.NEXT_PUBLIC_EASYPAISA ?? "0345 0000000" },
  { type: "raast", label: "Raast ID", title: "Laraib Creative", number: process.env.NEXT_PUBLIC_RAAST_ID ?? "0300 0000000" },
];

export const orderStatuses = [
  { value: "pending_payment", label: "Pending payment" },
  { value: "payment_verification", label: "Verifying payment" },
  { value: "confirmed", label: "Confirmed" },
  { value: "awaiting_fabric", label: "Awaiting fabric" },
  { value: "fabric_received", label: "Fabric received" },
  { value: "cutting", label: "Cutting" },
  { value: "stitching", label: "Stitching" },
  { value: "finishing", label: "Finishing" },
  { value: "quality_check", label: "Quality check" },
  { value: "ready", label: "Ready" },
  { value: "dispatched", label: "Out for delivery" },
  { value: "delivered", label: "Delivered" },
] as const;

export type OrderStatus = (typeof orderStatuses)[number]["value"] | "alteration" | "completed" | "cancelled";

export function statusLabel(status: string) {
  return orderStatuses.find((s) => s.value === status)?.label ?? status.replace(/_/g, " ");
}
