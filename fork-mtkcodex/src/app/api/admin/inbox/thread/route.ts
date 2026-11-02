import { NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/admin-auth';
import { getChatSession, visitorOnline } from '@/lib/chat';
import { leadForThread, listThread, markThreadRead } from '@/lib/inbox';
import { markAdminActive } from '@/lib/notify';
import { threadChannel } from '@/lib/lead-types';

export const dynamic = 'force-dynamic';

/** One conversation (any channel). Opening it clears the unread badge. */
export async function GET(req: Request) {
  const admin = await requireAdmin(req);
  if (admin instanceof Response) return admin;

  const params = new URL(req.url).searchParams;
  const key = params.get('key') || '';
  if (!threadChannel(key) || key.length > 300) return NextResponse.json({ error: 'Unknown conversation' }, { status: 400 });

  await markAdminActive();
  try {
    const session = key.startsWith('web:') ? await getChatSession(key.slice(4)) : null;
    const [messages, lead] = await Promise.all([listThread(key), leadForThread(key, session)]);
    if (params.get('read') !== '0') await markThreadRead(key, lead, session);
    return NextResponse.json({
      messages,
      lead: lead ? { ...lead, unread_count: key.startsWith('web:') ? lead.unread_count : 0 } : null,
      visitor: session
        ? {
            name: session.name,
            email: session.email,
            phone: session.phone,
            preferred_channel: session.preferred_channel,
            page: session.page,
            referrer: session.referrer,
            device: session.device,
            city: session.city,
            region: session.region,
            country: session.country,
            timezone: session.timezone,
            online: visitorOnline(session),
            typing: Boolean(session.visitor_typing_at && Date.now() - new Date(session.visitor_typing_at).getTime() < 6000),
            last_seen_at: session.last_seen_at,
            created_at: session.created_at,
          }
        : null,
    });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : 'Could not load the conversation' }, { status: 500 });
  }
}
