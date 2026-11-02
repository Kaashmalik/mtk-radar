import { NextResponse } from 'next/server';
import { agentName, createChatSession, resumeChat, toPublic } from '@/lib/chat';
import { chatError, noStore, readJson, text } from '@/lib/chat-http';
import { deviceFromUserAgent, isBot } from '@/lib/analytics';
import { geoFromRequest, isTimeZone } from '@/lib/geo';
import { listThread } from '@/lib/message-store';
import { adminOnline } from '@/lib/notify';
import { clientIp, rateLimited } from '@/lib/rate-limit';
import { trackablePath } from '@/lib/site-paths';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

/** Opens a chat (or resumes one from an emailed link) and returns the visitor token. */
export async function POST(req: Request) {
  const body = (await readJson(req)) || {};
  const userAgent = req.headers.get('user-agent') || '';
  if (isBot(userAgent)) return NextResponse.json({ error: 'Not available' }, { status: 403, headers: noStore });

  try {
    const resume = text(body.resume, 200);
    if (resume) {
      const resumed = await resumeChat(resume);
      if (resumed) {
        const messages = await listThread(`web:${resumed.session.id}`, { limit: 100 });
        return NextResponse.json(
          { token: resumed.token, messages: messages.map(toPublic), agent: { name: agentName(), online: await adminOnline() } },
          { headers: noStore },
        );
      }
    }

    if (await rateLimited(`chat-start:${clientIp(req)}`, 60 * 60 * 1000, 10)) {
      return NextResponse.json({ error: 'Too many new chats. Please try again later.' }, { status: 429, headers: noStore });
    }

    const tz = text(body.timezone, 64);
    const { token } = await createChatSession({
      geo: geoFromRequest(req),
      page: trackablePath(body.page) || '/',
      referrer: text(body.referrer, 120),
      device: deviceFromUserAgent(userAgent),
      timezone: isTimeZone(tz) ? tz : '',
    });
    return NextResponse.json({ token, messages: [], agent: { name: agentName(), online: await adminOnline() } }, { headers: noStore });
  } catch (error) {
    return chatError(error, 'Could not start the chat');
  }
}
