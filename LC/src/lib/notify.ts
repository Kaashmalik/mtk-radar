import "server-only";
import { createServiceClient } from "@/lib/supabase/server";
import { sendWhatsApp } from "@/lib/whatsapp";
import { handoverCode, reviewToken } from "@/lib/handover";
import { brand, statusLabel } from "@/lib/config";
import { rs } from "@/lib/utils";

// Statuses the customer hears about; internal steps (e.g. finishing) stay quiet.
const ANNOUNCED = new Set(["fabric_received", "cutting", "stitching", "quality_check", "ready", "dispatched", "alteration"]);

async function orderContact(orderId: string) {
  const { data } = await createServiceClient()
    .from("orders")
    .select("id, order_no, customer:customers(full_name, phone)")
    .eq("id", orderId)
    .single();
  const customer = data?.customer as unknown as { full_name: string; phone: string } | null;
  return data && customer ? { orderNo: data.order_no as string, name: customer.full_name.split(" ")[0], phone: customer.phone } : null;
}

export async function notifyOrderReceived(orderId: string, advance: number) {
  const c = await orderContact(orderId);
  if (c) await sendWhatsApp(c.phone, "order_received", [c.name, c.orderNo, rs(advance)], orderId);
}

export async function notifyConfirmed(orderId: string) {
  const c = await orderContact(orderId);
  if (c) await sendWhatsApp(c.phone, "order_confirmed", [c.name, c.orderNo], orderId);
}

export async function notifyStatus(orderId: string, status: string) {
  if (status === "delivered") return notifyDelivered(orderId);
  if (!ANNOUNCED.has(status)) return;
  const c = await orderContact(orderId);
  if (c) await sendWhatsApp(c.phone, "status_update", [c.orderNo, statusLabel(status)], orderId);
}

export async function notifyRiderOnTheWay(orderId: string, jobId: string, riderName: string) {
  const c = await orderContact(orderId);
  if (c) await sendWhatsApp(c.phone, "rider_on_the_way", [c.orderNo, riderName, handoverCode(jobId)], orderId);
}

export async function notifyDelivered(orderId: string) {
  const c = await orderContact(orderId);
  if (!c) return;
  const link = `https://${brand.domain}/review/${c.orderNo}?t=${reviewToken(orderId)}`;
  await sendWhatsApp(c.phone, "order_delivered", [c.name, c.orderNo, link], orderId);
}
