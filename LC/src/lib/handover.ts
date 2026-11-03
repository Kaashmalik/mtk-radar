import "server-only";
import { createHmac, timingSafeEqual } from "node:crypto";

function secret() {
  const s = process.env.HANDOVER_SECRET;
  if (s) return s;
  if (process.env.NEXT_PUBLIC_SUPABASE_URL) throw new Error("HANDOVER_SECRET is not configured");
  return "preview-only-secret";
}

/**
 * 4-digit code the customer gives the rider at pickup/delivery. Derived from the
 * job id so it never has to be stored; only the server (which holds the secret)
 * can produce or check it.
 */
export function handoverCode(jobId: string) {
  const digest = createHmac("sha256", secret()).update(jobId).digest();
  return String(digest.readUInt32BE(0) % 10000).padStart(4, "0");
}

/** Token for the "review your order" link sent after delivery. */
export function reviewToken(orderId: string) {
  return createHmac("sha256", secret()).update(`review:${orderId}`).digest("base64url").slice(0, 22);
}

export function checkReviewToken(orderId: string, token: string) {
  const expected = Buffer.from(reviewToken(orderId));
  const given = Buffer.from(token);
  return expected.length === given.length && timingSafeEqual(expected, given);
}

export function checkHandoverCode(jobId: string, code: string) {
  const expected = Buffer.from(handoverCode(jobId));
  const given = Buffer.from(code.trim().padStart(4, "0").slice(0, 4));
  return expected.length === given.length && timingSafeEqual(expected, given);
}
