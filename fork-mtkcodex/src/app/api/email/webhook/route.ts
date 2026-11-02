import { NextResponse } from 'next/server';
import { receivingConfigured, verifyResendWebhook } from '@/lib/email';
import { recordInboundEmail } from '@/lib/inbox';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

/**
 * Resend `email.received` webhook. The signature is checked against the raw
 * body; the email itself is then fetched from Resend's Received emails API.
 * Resend keeps the email even if this endpoint fails, and retries.
 */
export async function POST(req: Request) {
  if (!receivingConfigured()) return new Response('Not configured', { status: 404 });

  const raw = await req.text();
  const valid = verifyResendWebhook(raw, {
    id: req.headers.get('svix-id'),
    timestamp: req.headers.get('svix-timestamp'),
    signature: req.headers.get('svix-signature'),
  });
  if (!valid) return new Response('Invalid signature', { status: 401 });

  let event: { type?: string; data?: { email_id?: string } };
  try {
    event = JSON.parse(raw);
  } catch {
    return new Response('Bad JSON', { status: 400 });
  }
  if (event.type !== 'email.received' || !event.data?.email_id) return NextResponse.json({ ignored: true });

  try {
    await recordInboundEmail(event.data.email_id);
  } catch (error) {
    console.error('email: failed to store inbound email', error instanceof Error ? error.message : error);
    // 500 so Resend retries; duplicates are ignored by external_id.
    return NextResponse.json({ error: 'Processing failed' }, { status: 500 });
  }
  return NextResponse.json({ ok: true });
}
