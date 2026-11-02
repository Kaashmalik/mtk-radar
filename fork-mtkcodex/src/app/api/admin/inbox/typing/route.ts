import { NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/admin-auth';
import { setAgentTyping } from '@/lib/chat';

export const dynamic = 'force-dynamic';

/** Shows "Kashif is typing…" in the visitor's chat for a few seconds. */
export async function POST(req: Request) {
  const session = await requireAdmin(req);
  if (session instanceof Response) return session;

  let key = '';
  try {
    key = String(((await req.json()) as { key?: unknown }).key || '');
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }
  if (!/^web:[0-9a-f-]{36}$/i.test(key)) return NextResponse.json({ ok: false });
  await setAgentTyping(key.slice(4)).catch(() => undefined);
  return NextResponse.json({ ok: true });
}
