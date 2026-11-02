import { NextResponse } from 'next/server';
import { visitorSend } from '@/lib/chat';
import { chatError, noStore, readJson, sessionFromRequest, text } from '@/lib/chat-http';
import { clientIp, rateLimited } from '@/lib/rate-limit';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(req: Request) {
  const body = await readJson(req);
  if (!body) return NextResponse.json({ error: 'Invalid request' }, { status: 400, headers: noStore });
  // Honeypot field the widget never fills.
  if (text(body.website, 10)) return NextResponse.json({ messages: [] }, { headers: noStore });

  const session = await sessionFromRequest(req, body).catch(() => null);
  if (!session) return NextResponse.json({ error: 'Chat expired. Please start again.' }, { status: 401, headers: noStore });

  const [perChat, perIp] = await Promise.all([
    rateLimited(`chat-send:${session.id}`, 5 * 60 * 1000, 25),
    rateLimited(`chat-send-ip:${clientIp(req)}`, 10 * 60 * 1000, 60),
  ]);
  if (perChat || perIp) {
    return NextResponse.json({ error: 'You are sending messages very fast. Please wait a moment.' }, { status: 429, headers: noStore });
  }

  try {
    const messages = await visitorSend(session, text(body.body, 2000));
    return NextResponse.json({ messages }, { headers: noStore });
  } catch (error) {
    return chatError(error, 'Message not sent');
  }
}
