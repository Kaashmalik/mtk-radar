// Preview data for the admin dashboard, used only while Supabase is not connected.
import type { AdminOrder, AdminPayment, AdminReview, Category, Expense, Inquiry, MonthRow, OrderDetail, Partner, PartnerTxn, Rider, RiderJob } from "./admin";

const customers = [
  { full_name: "Ayesha K.", phone: "+923001112233", area: "Gulberg" },
  { full_name: "Hira M.", phone: "+923214445566", area: "DHA Phase 1–6" },
  { full_name: "Sana R.", phone: "+923337778899", area: "Cantt" },
  { full_name: "Maryam A.", phone: "+923451231234", area: "Model Town" },
  { full_name: "Zainab T.", phone: "+923009998877", area: "Askari" },
  { full_name: "Fatima S.", phone: "+923125556677", area: "Shadman" },
];

const statuses = ["payment_verification", "confirmed", "awaiting_fabric", "fabric_received", "cutting", "stitching", "stitching", "finishing", "quality_check", "ready", "dispatched", "pending_payment"];
const garmentsList = ["simple", "designer", "party", "kurti", "maxi", "designer"];

export const orders: AdminOrder[] = statuses.map((status, i) => ({
  id: `o${i}`,
  order_no: `LC-${1042 + i}`,
  status,
  tier: i % 4 === 0 ? "express" : i % 3 === 0 ? "priority" : "standard",
  fabric_method: i % 5 === 0 ? "dropoff" : "rider_pickup",
  zone_code: ["A", "B", "A", "B", "B", "A"][i % 6],
  pickup_date: `2026-11-${String(4 + (i % 6)).padStart(2, "0")}`,
  pickup_slot: "3:00 pm – 5:00 pm",
  total: [3100, 4600, 7400, 2400, 9800, 5200][i % 6],
  paid: status === "pending_payment" ? 0 : [1550, 2300, 3700, 1200, 4900, 2600][i % 6],
  created_at: `2026-11-0${1 + (i % 3)}T10:00:00Z`,
  customer: customers[i % customers.length],
  items: [{ garment_slug: garmentsList[i % garmentsList.length], qty: 1 + (i % 2) }],
}));

export const payments: AdminPayment[] = [
  { id: "p1", order_id: "o0", method: "jazzcash", amount: 1550, kind: "advance", txn_id: "JC88213", sender_name: "Ayesha K.", proof_url: null, submitted_via: "website", status: "pending", created_at: "2026-11-03T09:12:00Z", order: { order_no: "LC-1042", total: 3100 } },
  { id: "p2", order_id: "o6", method: "bank", amount: 2600, kind: "advance", txn_id: null, sender_name: "Fatima S.", proof_url: null, submitted_via: "whatsapp", status: "pending", created_at: "2026-11-03T11:40:00Z", order: { order_no: "LC-1048", total: 5200 } },
  { id: "p3", order_id: "o11", method: "easypaisa", amount: 3700, kind: "advance", txn_id: "EP55120", sender_name: "Sana R.", proof_url: null, submitted_via: "website", status: "pending", created_at: "2026-11-03T13:05:00Z", order: { order_no: "LC-1053", total: 7400 } },
];

export const categories: Category[] = [
  ["Production", "Karigar wages"], ["Production", "Threads & lining"], ["Production", "Buttons, lace & trims"], ["Production", "Machine repair"],
  ["Delivery", "Rider salaries"], ["Delivery", "Fuel allowance"], ["Delivery", "Packaging & bags"],
  ["Premises", "Rent"], ["Premises", "Electricity (LESCO)"], ["Premises", "Internet"],
  ["Staff", "Staff salaries"], ["Marketing", "Meta / Instagram ads"], ["Marketing", "Photography"],
  ["Technology", "Domain & hosting"], ["Admin & legal", "Bank & wallet charges"], ["Losses", "Rework"], ["Other", "Miscellaneous"],
].map(([grp, name], i) => ({ id: `c${i}`, grp, name }));

const e = (i: number, cat: number, amount: number, vendor: string, day: number, partner: string | null = null): Expense => ({
  id: `e${i}`,
  spent_on: `2026-11-${String(day).padStart(2, "0")}`,
  amount,
  vendor,
  notes: null,
  receipt_url: null,
  status: amount > 10000 && i === 2 ? "pending_approval" : "approved",
  category: { grp: categories[cat].grp, name: categories[cat].name },
  partner: partner ? { name: partner } : null,
});

export const expenses: Expense[] = [
  e(1, 7, 45000, "Workshop landlord", 1),
  e(2, 0, 38000, "Karigars (week 1)", 2),
  e(3, 1, 6200, "Azam Cloth Market", 2, "Stitching Partner"),
  e(4, 11, 15000, "Meta ads", 3, "Tech & Online Partner"),
  e(5, 4, 22000, "Rider Ali", 1),
  e(6, 5, 4500, "Fuel", 3),
  e(7, 8, 9800, "LESCO", 3),
  e(8, 13, 3200, "Vercel / domain", 1, "Tech & Online Partner"),
];

export const partners: Partner[] = [
  { id: "pa", name: "Tech & Online Partner", role: "tech_online", share_percent: 50 },
  { id: "pb", name: "Stitching Partner", role: "stitching", share_percent: 50 },
];

export const partnerTxns: PartnerTxn[] = [
  { id: "t1", partner_id: "pa", type: "capital", amount: 150000, happened_on: "2026-10-01", notes: "Laptop, domain, launch ads" },
  { id: "t2", partner_id: "pb", type: "capital", amount: 250000, happened_on: "2026-10-01", notes: "Machines and workshop setup" },
  { id: "t3", partner_id: "pa", type: "drawing", amount: 20000, happened_on: "2026-11-02", notes: null },
  { id: "t4", partner_id: "pb", type: "drawing", amount: 30000, happened_on: "2026-11-02", notes: null },
];

export const pnl: MonthRow[] = [
  { month: "2026-06", revenue: 210000, expenses: 168000, net_profit: 42000 },
  { month: "2026-07", revenue: 265000, expenses: 181000, net_profit: 84000 },
  { month: "2026-08", revenue: 248000, expenses: 176000, net_profit: 72000 },
  { month: "2026-09", revenue: 312000, expenses: 199000, net_profit: 113000 },
  { month: "2026-10", revenue: 398000, expenses: 236000, net_profit: 162000 },
  { month: "2026-11", revenue: 121000, expenses: 143700, net_profit: -22700 },
];

export const riderJobs: RiderJob[] = orders.slice(0, 6).map((o, i) => ({
  id: `j${i}`,
  type: i % 3 === 2 ? "delivery" : i % 3 === 1 ? "measurement" : "pickup",
  scheduled_date: "2026-11-04",
  slot: ["11:00 am – 1:00 pm", "3:00 pm – 5:00 pm", "6:00 pm – 8:00 pm"][i % 3],
  status: i === 0 ? "en_route" : "assigned",
  cash_to_collect: i % 3 === 2 ? o.total - o.paid : 0,
  rider_id: i % 2 ? "r2" : "r1",
  notes: i % 3 === 1 ? "Take measurements and collect fabric" : null,
  rider: { full_name: i % 2 ? "Bilal" : "Ali" },
  order: { order_no: o.order_no, zone_code: o.zone_code, customer: { full_name: o.customer!.full_name, area: o.customer!.area, address: "House 12, Street 4" } },
}));

export const riders: Rider[] = [
  { id: "r1", full_name: "Ali", phone: "+923001234567", zones: ["A", "B"], is_active: true, bike_no: "LEB-1234", profile_id: null },
  { id: "r2", full_name: "Bilal", phone: "+923217654321", zones: ["B", "C"], is_active: true, bike_no: "LEC-5678", profile_id: null },
];

export function orderDetail(id: string): OrderDetail | null {
  const o = orders.find((x) => x.id === id);
  if (!o) return null;
  return {
    ...o,
    subtotal: o.total - 300,
    urgency_fee: 0,
    delivery_fee: 300,
    promised_date: "2026-11-12",
    showcase_consent: true,
    notes: null,
    customer: { id: "c1", ...o.customer!, address: "House 12, Street 4", landmark: "Near the park" },
    items: [
      {
        id: "it1",
        garment_slug: o.items[0].garment_slug,
        qty: o.items[0].qty,
        price: o.total - 300,
        options: { neckline: "v-neck", sleeves: "three-quarter", daman: "curved", trouser: "cigarette", addons: ["lining"] },
        measurement_snapshot: { method: "standard_size", size: "M", fit: "regular", notes: "Sleeves 1 inch longer" },
        reference_images: [],
      },
    ],
    payments: [{ id: "p1", method: "jazzcash", amount: o.paid, kind: "advance", status: "verified", proof_url: null, created_at: o.created_at }],
    history: [
      { id: 1, from_status: null, to_status: "payment_verification", note: "Order placed on website", photo_url: null, created_at: o.created_at },
      { id: 2, from_status: "payment_verification", to_status: "confirmed", note: "Payment verified", photo_url: null, created_at: o.created_at },
    ],
    jobs: [{ id: "j0", type: "pickup", scheduled_date: o.pickup_date ?? "2026-11-05", slot: o.pickup_slot, status: "done", cash_to_collect: 0, rider_id: "r1", proof_photos: [] }],
    custody: [],
  };
}

export const reviews: AdminReview[] = [
  { id: "rv1", customer_name: "Sample customer", area: "Gulberg", rating: 5, fit: 5, finishing: 5, on_time: 4, body: "Preview text — new reviews wait here for moderation.", media: [], status: "pending", reply: null, featured: false, created_at: "2026-11-03T10:00:00Z", order: { order_no: "LC-1040" } },
];

export const inquiries: Inquiry[] = [
  { id: "i1", type: "bridal", name: "Rabia N.", phone: "+923004561234", message: "Walima maxi in February, need consultation for design and fabric.", status: "new", created_at: "2026-11-03T08:00:00Z" },
  { id: "i2", type: "bulk", name: "Amna J.", phone: "+923217894561", message: "8 suits for family wedding, matching designs.", status: "contacted", created_at: "2026-11-02T15:30:00Z" },
  { id: "i3", type: "alteration", name: "Nida F.", phone: "+923331237894", message: "Need 3 ready-made suits taken in at the waist.", status: "new", created_at: "2026-11-02T12:10:00Z" },
];
