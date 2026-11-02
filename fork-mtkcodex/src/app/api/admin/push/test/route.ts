import { NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/admin-auth';
import { notifyOwner } from '@/lib/notify';

export const dynamic = 'force-dynamic';

/** Sends a test alert to every registered device and Telegram. */
export async function POST(req: Request) {
  const session = await requireAdmin(req);
  if (session instanceof Response) return session;
  const result = await notifyOwner({
    title: 'MTK Codex alerts are on',
    body: 'New chats, replies and enquiries will appear here.',
    url: '/admin/inbox',
    tag: 'test',
  });
  return NextResponse.json(result);
}
