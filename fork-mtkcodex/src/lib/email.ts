import { createHmac, timingSafeEqual } from 'node:crypto';

/**
 * Email through Resend: sending, and receiving replies into the CRM inbox.
 *
 *   RESEND_API_KEY         API key (sending + reading received mail)
 *   EMAIL_FROM             "Kashif at MTK Codex <hello@mtkcodex.tech>" (verified domain)
 *   EMAIL_REPLY_DOMAIN     domain with Resend's receiving MX record, e.g. mtkcodex.tech
 *   RESEND_WEBHOOK_SECRET  signing secret of the `email.received` webhook (whsec_…)
 *   EMAIL_FORWARD_TO       optional: also forward every inbound email to this address
 *
 * Replies are routed by a per-lead reply address (r-<token>@EMAIL_REPLY_DOMAIN),
 * falling back to matching the sender's address.
 */

const env = (key: string) => (process.env[key] || '').trim();

export function emailConfigured(): boolean {
  return Boolean(env('RESEND_API_KEY') && env('EMAIL_FROM'));
}

export function receivingConfigured(): boolean {
  return Boolean(env('RESEND_API_KEY') && env('RESEND_WEBHOOK_SECRET') && env('EMAIL_REPLY_DOMAIN'));
}

export function fromAddress(): string {
  return env('EMAIL_FROM') || 'MTK Codex Website <onboarding@resend.dev>';
}

export function replyAddress(token: string | null | undefined): string | undefined {
  const domain = env('EMAIL_REPLY_DOMAIN');
  return token && domain ? `r-${token}@${domain}` : undefined;
}

/** Finds our routing token in any recipient like r-abc123@mtkcodex.tech. */
export function tokenFromRecipients(addresses: string[]): string | null {
  const domain = env('EMAIL_REPLY_DOMAIN').toLowerCase();
  for (const raw of addresses) {
    const { email } = parseAddress(raw);
    const match = email.match(/^r-([a-z0-9]{8,32})@(.+)$/);
    if (match && (!domain || match[2] === domain)) return match[1];
  }
  return null;
}

/** "Jane Doe <jane@x.com>" → { name: 'Jane Doe', email: 'jane@x.com' } */
export function parseAddress(value: string): { name: string; email: string } {
  const match = value.match(/^\s*"?([^"<]*?)"?\s*<([^>]+)>\s*$/);
  if (match) return { name: match[1].trim(), email: match[2].trim().toLowerCase() };
  return { name: '', email: value.trim().toLowerCase() };
}

const escapeHtml = (text: string) =>
  text.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] || c);

function htmlBody(text: string): string {
  const paragraphs = escapeHtml(text)
    .split(/\n{2,}/)
    .map((p) => `<p style="margin:0 0 14px">${p.replace(/\n/g, '<br>')}</p>`)
    .join('');
  return `<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.55;color:#0f2a35">${paragraphs}</div>`;
}

export type OutgoingEmail = {
  to: string;
  subject: string;
  text: string;
  replyTo?: string;
  /** Message-ID of the email being answered, so clients thread the reply. */
  inReplyTo?: string;
};

export async function sendEmail(email: OutgoingEmail): Promise<{ id: string }> {
  if (!env('RESEND_API_KEY')) throw new Error('Email is not configured (RESEND_API_KEY).');
  const headers: Record<string, string> = {};
  if (email.inReplyTo) {
    headers['In-Reply-To'] = email.inReplyTo;
    headers.References = email.inReplyTo;
  }
  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { Authorization: `Bearer ${env('RESEND_API_KEY')}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      from: fromAddress(),
      to: [email.to],
      subject: email.subject.slice(0, 200),
      text: email.text,
      html: htmlBody(email.text),
      ...(email.replyTo ? { reply_to: email.replyTo } : {}),
      ...(Object.keys(headers).length ? { headers } : {}),
    }),
    cache: 'no-store',
  });
  const data = (await res.json().catch(() => ({}))) as { id?: string; message?: string };
  if (!res.ok || !data.id) throw new Error(`Email: ${data.message || `HTTP ${res.status}`}`);
  return { id: data.id };
}

/**
 * Verifies a Resend (Svix) webhook: HMAC-SHA256 over "<id>.<timestamp>.<body>"
 * with the base64 secret after "whsec_", compared against every "v1,<sig>"
 * in the signature header, within a five-minute window.
 */
export function verifyResendWebhook(
  rawBody: string,
  headers: { id: string | null; timestamp: string | null; signature: string | null },
  secret = env('RESEND_WEBHOOK_SECRET'),
  now = Date.now(),
): boolean {
  if (!secret || !headers.id || !headers.timestamp || !headers.signature) return false;
  const ts = Number(headers.timestamp);
  if (!Number.isFinite(ts) || Math.abs(now / 1000 - ts) > 5 * 60) return false;
  const key = Buffer.from(secret.replace(/^whsec_/, ''), 'base64');
  const expected = createHmac('sha256', key).update(`${headers.id}.${headers.timestamp}.${rawBody}`).digest();
  return headers.signature.split(' ').some((part) => {
    const [version, value] = part.split(',');
    if (version !== 'v1' || !value) return false;
    const given = Buffer.from(value, 'base64');
    return given.length === expected.length && timingSafeEqual(given, expected);
  });
}

export type ReceivedEmail = {
  id: string;
  from: string;
  to: string[];
  subject: string;
  text: string | null;
  html: string | null;
  message_id: string;
  created_at: string;
  reply_to?: string[];
  authentication?: { spf?: string; dkim?: string; dmarc?: string } | null;
  attachments?: { filename: string; size: number }[];
};

/** Webhooks carry metadata only; the body comes from the Received emails API. */
export async function getReceivedEmail(id: string): Promise<ReceivedEmail> {
  const res = await fetch(`https://api.resend.com/emails/receiving/${encodeURIComponent(id)}`, {
    headers: { Authorization: `Bearer ${env('RESEND_API_KEY')}` },
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(`Resend receiving ${res.status}: ${(await res.text()).slice(0, 200)}`);
  return (await res.json()) as ReceivedEmail;
}

/** Plain text from HTML, good enough for a chat bubble. */
export function htmlToText(html: string): string {
  return html
    .replace(/<(style|script)[\s\S]*?<\/\1>/gi, '')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/(p|div|li|tr|h\d)>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/** Drops the quoted history under a reply ("On … wrote:", "> …", Outlook headers). */
export function stripQuotedReply(text: string): string {
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  const kept: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const next = lines[i + 1] || '';
    // Gmail sometimes wraps "On <date>, <name> wrote:" over two lines.
    if (/^\s*On .{4,200}wrote:\s*$/i.test(line) || (/^\s*On .{4,200}$/i.test(line) && /wrote:\s*$/i.test(next))) break;
    if (/^-{2,}\s*Original Message\s*-{2,}/i.test(line)) break;
    if (/^\s*From:\s.+/i.test(line) && kept.length && /^\s*(Sent|Date):\s/i.test(next)) break;
    if (/^\s*>/.test(line)) continue;
    kept.push(line);
  }
  return kept.join('\n').trim();
}
