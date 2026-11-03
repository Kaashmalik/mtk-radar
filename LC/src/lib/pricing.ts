import { addons, designOptions, garments, tiers, zones } from "./config";

export type OrderSelection = {
  garment: string;
  options: Record<string, string>;
  addons: string[];
  qty: number;
  tier: (typeof tiers)[number]["value"];
  fabricMethod: "rider_pickup" | "courier" | "dropoff";
  zone?: "A" | "B" | "C";
};

export type Coupon = { code: string; kind: "percent" | "flat"; value: number; min_order: number; max_discount: number | null };

export function couponDiscount(coupon: Coupon | null, subtotal: number) {
  if (!coupon || subtotal < coupon.min_order) return 0;
  const raw = coupon.kind === "percent" ? Math.round((subtotal * coupon.value) / 100) : coupon.value;
  return Math.min(raw, coupon.max_discount ?? Infinity, subtotal);
}

export function quote(sel: OrderSelection, coupon: Coupon | null = null) {
  const garment = garments.find((g) => g.slug === sel.garment) ?? garments[0];
  const optionTotal = designOptions.reduce((sum, group) => {
    const picked = group.options.find((o) => o.value === sel.options[group.key]);
    return sum + (picked?.price ?? 0);
  }, 0);
  const addonTotal = addons.filter((a) => sel.addons.includes(a.value)).reduce((s, a) => s + a.price, 0);

  const qty = Math.max(1, sel.qty);
  const unit = garment.basePrice + optionTotal + addonTotal;
  const subtotal = unit * qty;
  const urgencyFee = (tiers.find((t) => t.value === sel.tier)?.fee ?? 0) * qty;
  const discount = couponDiscount(coupon, subtotal);

  let deliveryFee = 0;
  if (sel.fabricMethod === "rider_pickup" && sel.zone) {
    const zone = zones.find((z) => z.code === sel.zone)!;
    // one fee for pickup + one for return, waived above the zone threshold
    deliveryFee = subtotal >= zone.freeAbove ? 0 : zone.fee * 2;
  }

  const total = subtotal - discount + urgencyFee + deliveryFee;
  const advance = Math.ceil(total / 2 / 10) * 10;
  return { unit, subtotal, discount, urgencyFee, deliveryFee, total, advance, days: garment.days };
}

const TIER_DAYS = { standard: null, priority: 5, express: 2 } as const;

/**
 * Working-day estimate for delivery: stitching starts the day after the fabric
 * reaches us; Sundays are off. Returns an ISO date (yyyy-mm-dd).
 */
export function estimateDelivery(sel: Pick<OrderSelection, "garment" | "tier">, fabricDate: string) {
  const garment = garments.find((g) => g.slug === sel.garment) ?? garments[0];
  let days: number = TIER_DAYS[sel.tier] ?? garment.days;
  if (sel.tier !== "standard") days = Math.min(days, garment.days);
  const d = new Date(`${fabricDate}T12:00:00Z`);
  while (days > 0) {
    d.setUTCDate(d.getUTCDate() + 1);
    if (d.getUTCDay() !== 0) days--;
  }
  return d.toISOString().slice(0, 10);
}

export function formatDay(iso: string) {
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-PK", { weekday: "short", day: "numeric", month: "short" });
}
