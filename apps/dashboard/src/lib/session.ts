/**
 * Stateless, signed dashboard sessions.
 *
 * The browser holds an HttpOnly cookie. It contains the reviewer's personal
 * token, but JavaScript can never read it: all interactive API traffic goes
 * through the same-origin /api/backend proxy, which attaches the token
 * server-side. The proxy only needs a valid HMAC and an unexpired payload.
 *
 * Uses Web Crypto so the exact same verification works in Next's proxy
 * runtime and in Node route handlers. There is deliberately no fallback
 * secret: if MTK_SESSION_SECRET is missing, authentication fails closed.
 */

export const SESSION_COOKIE = "mtk_session";
export const SESSION_TTL_SECONDS = 12 * 60 * 60;

export type DashboardSession = {
  actor: string;
  token: string;
  exp: number;
};

const encoder = new TextEncoder();
const decoder = new TextDecoder();

function base64url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function fromBase64url(value: string): Uint8Array | null {
  try {
    const padded = value.replace(/-/g, "+").replace(/_/g, "/")
      .padEnd(Math.ceil(value.length / 4) * 4, "=");
    const binary = atob(padded);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return bytes;
  } catch {
    return null;
  }
}

async function hmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

export async function createSessionCookie(
  actor: string,
  token: string,
  secret: string,
  ttlSeconds = SESSION_TTL_SECONDS,
): Promise<string> {
  const payload = base64url(encoder.encode(JSON.stringify({
    actor,
    token,
    exp: Date.now() + ttlSeconds * 1000,
  } satisfies DashboardSession)));
  const signature = await crypto.subtle.sign("HMAC", await hmacKey(secret), encoder.encode(payload));
  return `${payload}.${base64url(new Uint8Array(signature))}`;
}

export async function verifySessionCookie(
  value: string | undefined | null,
  secret: string,
): Promise<DashboardSession | null> {
  if (!value || !secret) return null;
  const [payload, signatureText, extra] = value.split(".");
  if (!payload || !signatureText || extra) return null;
  const signature = fromBase64url(signatureText);
  if (!signature) return null;

  let valid = false;
  try {
    valid = await crypto.subtle.verify(
      "HMAC",
      await hmacKey(secret),
      signature as unknown as BufferSource,
      encoder.encode(payload),
    );
  } catch {
    return null;
  }
  if (!valid) return null;

  const raw = fromBase64url(payload);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(decoder.decode(raw)) as Partial<DashboardSession>;
    if (typeof parsed.actor !== "string" || parsed.actor.length < 2) return null;
    if (typeof parsed.token !== "string" || parsed.token.length < 20) return null;
    if (typeof parsed.exp !== "number" || parsed.exp <= Date.now()) return null;
    return { actor: parsed.actor, token: parsed.token, exp: parsed.exp };
  } catch {
    return null;
  }
}

export function sessionSecret(): string | null {
  const value = (process.env.MTK_SESSION_SECRET ?? "").trim();
  return value.length >= 32 ? value : null;
}

export function cookieOptions(secure: boolean): {
  httpOnly: true;
  secure: boolean;
  sameSite: "strict";
  path: "/";
  maxAge: number;
} {
  return {
    httpOnly: true,
    secure,
    sameSite: "strict",
    path: "/",
    maxAge: SESSION_TTL_SECONDS,
  };
}

/** True when the user-facing request arrived over HTTPS (directly or via a
 * TLS-terminating proxy). Local `next start` on http:// must still be able to
 * set a non-Secure cookie for the E2E suite. */
export function requestIsSecure(request: Request): boolean {
  const forwarded = request.headers.get("x-forwarded-proto");
  if (forwarded) return forwarded.split(",")[0].trim().toLowerCase() === "https";
  return new URL(request.url).protocol === "https:";
}
