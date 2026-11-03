import "server-only";
import { createServiceClient, isSupabaseConfigured } from "@/lib/supabase/server";

/**
 * WhatsApp Business Cloud API (Meta). Optional: without credentials every
 * message is logged as "skipped" and staff use the click-to-chat buttons instead.
 *
 * Each template must be created and approved in WhatsApp Manager with the
 * same name and body parameters in the same order as below.
 */
const token = process.env.WHATSAPP_TOKEN;
const phoneNumberId = process.env.WHATSAPP_PHONE_NUMBER_ID;
const lang = process.env.WHATSAPP_TEMPLATE_LANG ?? "en";

export type Template =
  | "order_received" //     {{1}} name, {{2}} order no, {{3}} advance amount
  | "order_confirmed" //    {{1}} name, {{2}} order no
  | "status_update" //      {{1}} order no, {{2}} new status
  | "rider_on_the_way" //   {{1}} order no, {{2}} rider name, {{3}} handover code
  | "order_delivered"; //   {{1}} name, {{2}} order no, {{3}} review link

export async function sendWhatsApp(to: string, template: Template, params: string[], orderId?: string) {
  const recipient = to.replace(/\D/g, "");
  let status: "sent" | "failed" | "skipped" = "skipped";
  let error: string | null = null;

  if (token && phoneNumberId) {
    try {
      const res = await fetch(`https://graph.facebook.com/v21.0/${phoneNumberId}/messages`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          messaging_product: "whatsapp",
          to: recipient,
          type: "template",
          template: {
            name: template,
            language: { code: lang },
            components: [{ type: "body", parameters: params.map((text) => ({ type: "text", text })) }],
          },
        }),
      });
      status = res.ok ? "sent" : "failed";
      if (!res.ok) error = (await res.text()).slice(0, 500);
    } catch (e) {
      status = "failed";
      error = e instanceof Error ? e.message : String(e);
    }
  }

  if (isSupabaseConfigured) {
    await createServiceClient()
      .from("notifications")
      .insert({ order_id: orderId ?? null, channel: "whatsapp", recipient, template, status, error });
  }
  return status;
}
