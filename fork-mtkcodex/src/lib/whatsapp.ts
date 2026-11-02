import { createHmac, timingSafeEqual } from 'node:crypto';

/**
 * WhatsApp Business Cloud API (Meta). Optional: the inbox turns on when these
 * env vars are set. See docs/CRM.md → "WhatsApp inbox" for setup.
 *
 *   WHATSAPP_TOKEN            permanent system-user access token
 *   WHATSAPP_PHONE_NUMBER_ID  the sending number's id (not the number itself)
 *   WHATSAPP_APP_SECRET       app secret, used to verify webhook signatures
 *   WHATSAPP_VERIFY_TOKEN     any random string, also entered in the Meta dashboard
 *   WHATSAPP_API_VERSION      Graph API version (default v23.0)
 */

const env = (key: string) => (process.env[key] || '').trim();

export function whatsappConfigured(): boolean {
  return Boolean(env('WHATSAPP_TOKEN') && env('WHATSAPP_PHONE_NUMBER_ID') && env('WHATSAPP_APP_SECRET'));
}

export function whatsappVerifyToken(): string {
  return env('WHATSAPP_VERIFY_TOKEN');
}

/** Checks Meta's `X-Hub-Signature-256: sha256=<hex>` header against the raw body. */
export function verifyWebhookSignature(rawBody: string, header: string | null, secret = env('WHATSAPP_APP_SECRET')): boolean {
  if (!secret || !header?.startsWith('sha256=')) return false;
  const expected = createHmac('sha256', secret).update(rawBody, 'utf8').digest();
  const given = Buffer.from(header.slice(7), 'hex');
  return given.length === expected.length && timingSafeEqual(given, expected);
}

export type InboundMessage = {
  wamid: string;
  from: string;
  profileName: string;
  timestamp: string;
  type: string;
  body: string;
};

export type StatusUpdate = {
  wamid: string;
  recipient: string;
  status: 'sent' | 'delivered' | 'read' | 'failed';
  error: string;
};

type WebhookPayload = {
  entry?: {
    changes?: {
      field?: string;
      value?: {
        contacts?: { wa_id?: string; profile?: { name?: string } }[];
        messages?: Record<string, unknown>[];
        statuses?: Record<string, unknown>[];
      };
    }[];
  }[];
};

/** Readable text for any inbound message type. */
function messageText(message: Record<string, unknown>): string {
  const type = String(message.type || '');
  const part = (message[type] || {}) as Record<string, unknown>;
  if (type === 'text') return String((part as { body?: string }).body || '');
  if (type === 'button') return String((part as { text?: string }).text || '');
  if (type === 'interactive') {
    const reply = (part.button_reply || part.list_reply || {}) as { title?: string };
    return String(reply.title || '[interactive reply]');
  }
  if (type === 'reaction') return `Reacted ${(part as { emoji?: string }).emoji || ''}`.trim();
  if (type === 'location') return '[location shared]';
  const caption = (part as { caption?: string }).caption;
  return `[${type || 'message'}]${caption ? ` ${caption}` : ''}`;
}

export function parseWebhook(payload: unknown): { messages: InboundMessage[]; statuses: StatusUpdate[] } {
  const messages: InboundMessage[] = [];
  const statuses: StatusUpdate[] = [];
  for (const entry of (payload as WebhookPayload)?.entry || []) {
    for (const change of entry.changes || []) {
      const value = change.value;
      if (!value) continue;
      const names = new Map((value.contacts || []).map((c) => [c.wa_id || '', c.profile?.name || '']));
      for (const message of value.messages || []) {
        const from = String(message.from || '').replace(/\D/g, '');
        const wamid = String(message.id || '');
        if (!from || !wamid) continue;
        messages.push({
          wamid,
          from,
          profileName: names.get(from) || '',
          timestamp: message.timestamp
            ? new Date(Number(message.timestamp) * 1000).toISOString()
            : new Date().toISOString(),
          type: String(message.type || 'text'),
          body: messageText(message).slice(0, 4000),
        });
      }
      for (const status of value.statuses || []) {
        const state = String(status.status || '');
        if (!['sent', 'delivered', 'read', 'failed'].includes(state)) continue;
        const errors = (status.errors || []) as { title?: string; message?: string }[];
        statuses.push({
          wamid: String(status.id || ''),
          recipient: String(status.recipient_id || '').replace(/\D/g, ''),
          status: state as StatusUpdate['status'],
          error: errors.map((e) => e.message || e.title || '').filter(Boolean).join('; ').slice(0, 300),
        });
      }
    }
  }
  return { messages, statuses };
}

/** Matches an opt-out reply ("STOP", "unsubscribe", Roman Urdu "band karo"). */
export function isOptOut(text: string): boolean {
  return /^\s*(stop|stop all|unsubscribe|opt out|opt-out|band karo|message na karein|no more messages)\s*[.!]*\s*$/i.test(text);
}

type SendResult = { wamid: string };

async function graph(body: Record<string, unknown>): Promise<SendResult> {
  const version = env('WHATSAPP_API_VERSION') || 'v23.0';
  const res = await fetch(`https://graph.facebook.com/${version}/${env('WHATSAPP_PHONE_NUMBER_ID')}/messages`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${env('WHATSAPP_TOKEN')}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ messaging_product: 'whatsapp', recipient_type: 'individual', ...body }),
    cache: 'no-store',
  });
  const data = (await res.json().catch(() => ({}))) as {
    messages?: { id?: string }[];
    error?: { message?: string; error_data?: { details?: string } };
  };
  if (!res.ok || !data.messages?.[0]?.id) {
    const detail = data.error?.error_data?.details || data.error?.message || `HTTP ${res.status}`;
    throw new Error(`WhatsApp: ${detail}`);
  }
  return { wamid: data.messages[0].id };
}

export function sendText(to: string, text: string): Promise<SendResult> {
  return graph({ to, type: 'text', text: { preview_url: false, body: text } });
}

/** Business-initiated messages (outside the 24h window) must use an approved template. */
export function sendTemplate(to: string, name: string, language: string, params: string[] = []): Promise<SendResult> {
  return graph({
    to,
    type: 'template',
    template: {
      name,
      language: { code: language },
      ...(params.length
        ? { components: [{ type: 'body', parameters: params.map((text) => ({ type: 'text', text })) }] }
        : {}),
    },
  });
}

export function defaultTemplate(): { name: string; language: string } {
  return { name: env('WHATSAPP_TEMPLATE_NAME'), language: env('WHATSAPP_TEMPLATE_LANG') || 'en' };
}
