import { NextResponse } from 'next/server';
import { identifyVisitor } from '@/lib/chat';
import { chatError, noStore, readJson, sessionFromRequest, text } from '@/lib/chat-http';
import { rateLimited } from '@/lib/rate-limit';
import type { PreferredChannel } from '@/lib/lead-types';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const CHANNELS: PreferredChannel[] = ['email', 'whatsapp', 'call', 'chat'];

/** The visitor shares how to reach them; this links the chat to a CRM lead. */
export async function POST(req: Request) {
  const body = await readJson(req);
  if (!body) return NextResponse.json({ error: 'Invalid request' }, { status: 400, headers: noStore });
  if (text(body.website, 10)) return NextResponse.json({ ok: true }, { headers: noStore });

  const session = await sessionFromRequest(req, body).catch(() => null);
  if (!session) return NextResponse.json({ error: 'Chat expired. Please start again.' }, { status: 401, headers: noStore });
  if (await rateLimited(`chat-identify:${session.id}`, 60 * 60 * 1000, 6)) {
    return NextResponse.json({ error: 'Too many attempts.' }, { status: 429, headers: noStore });
  }

  const preferred = text(body.preferred_channel, 10) as PreferredChannel;
  try {
    await identifyVisitor(session, {
      name: text(body.name, 120),
      email: text(body.email, 200),
      phone: text(body.phone, 40),
      preferred_channel: CHANNELS.includes(preferred) ? preferred : '',
    });
    return NextResponse.json({ ok: true }, { headers: noStore });
  } catch (error) {
    return chatError(error, 'Could not save your details');
  }
}
