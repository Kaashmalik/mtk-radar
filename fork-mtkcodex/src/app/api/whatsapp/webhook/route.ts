import { NextResponse } from 'next/server';
import { applyWhatsAppStatus, recordInboundWhatsApp } from '@/lib/inbox';
import { parseWebhook, verifyWebhookSignature, whatsappConfigured, whatsappVerifyToken } from '@/lib/whatsapp';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

/** Meta's one-time subscription handshake. */
export async function GET(req: Request) {
  const params = new URL(req.url).searchParams;
  const token = whatsappVerifyToken();
  if (token && params.get('hub.mode') === 'subscribe' && params.get('hub.verify_token') === token) {
    return new Response(params.get('hub.challenge') || '', { status: 200, headers: { 'Content-Type': 'text/plain' } });
  }
  return new Response('Forbidden', { status: 403 });
}

/**
 * Inbound messages and delivery receipts. The signature is checked against the
 * raw body before anything is parsed. Processing errors still return 200 so
 * Meta does not retry forever; duplicates are ignored by wamid anyway.
 */
export async function POST(req: Request) {
  if (!whatsappConfigured()) return new Response('Not configured', { status: 404 });

  const raw = await req.text();
  if (!verifyWebhookSignature(raw, req.headers.get('x-hub-signature-256'))) {
    return new Response('Invalid signature', { status: 401 });
  }

  let payload: unknown;
  try {
    payload = JSON.parse(raw);
  } catch {
    return new Response('Bad JSON', { status: 400 });
  }

  const { messages, statuses } = parseWebhook(payload);
  for (const message of messages) {
    try {
      await recordInboundWhatsApp(message);
    } catch (error) {
      console.error('whatsapp: failed to store inbound message', error instanceof Error ? error.message : error);
    }
  }
  for (const status of statuses) {
    try {
      await applyWhatsAppStatus(status);
    } catch (error) {
      console.error('whatsapp: failed to apply status', error instanceof Error ? error.message : error);
    }
  }

  return NextResponse.json({ ok: true });
}
