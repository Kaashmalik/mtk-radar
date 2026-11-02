import { NextResponse } from 'next/server';
import { pollChat } from '@/lib/chat';
import { chatError, noStore, sessionFromRequest } from '@/lib/chat-http';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

/** New messages since `after`, plus agent presence. Also the visitor's heartbeat. */
export async function GET(req: Request) {
  const session = await sessionFromRequest(req).catch(() => null);
  if (!session) return NextResponse.json({ error: 'Chat expired' }, { status: 401, headers: noStore });

  const params = new URL(req.url).searchParams;
  const after = params.get('after');
  const validAfter = after && !Number.isNaN(Date.parse(after)) ? new Date(after).toISOString() : null;
  try {
    return NextResponse.json(await pollChat(session, validAfter, params.get('typing') === '1'), { headers: noStore });
  } catch (error) {
    return chatError(error, 'Could not refresh the chat');
  }
}
