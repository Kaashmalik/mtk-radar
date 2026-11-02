import { NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/admin-auth';
import { sendFromDashboard } from '@/lib/inbox';
import { LeadError } from '@/lib/leads';

export const dynamic = 'force-dynamic';

export async function POST(req: Request) {
  const session = await requireAdmin(req);
  if (session instanceof Response) return session;

  let body: { key?: unknown; text?: unknown; subject?: unknown; template?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }
  if (typeof body.key !== 'string' || !body.key) {
    return NextResponse.json({ error: 'Conversation key is required' }, { status: 422 });
  }

  const raw = (body.template || null) as { name?: unknown; language?: unknown; params?: unknown } | null;
  const template =
    raw && typeof raw.name === 'string' && raw.name.trim()
      ? {
          name: raw.name.trim(),
          language: typeof raw.language === 'string' && raw.language ? raw.language : 'en',
          params: Array.isArray(raw.params) ? raw.params.filter((p): p is string => typeof p === 'string') : [],
        }
      : undefined;

  try {
    const message = await sendFromDashboard({
      key: body.key,
      text: typeof body.text === 'string' ? body.text : undefined,
      subject: typeof body.subject === 'string' ? body.subject : undefined,
      template,
    });
    return NextResponse.json({ message });
  } catch (error) {
    const status = error instanceof LeadError ? error.status : 502;
    return NextResponse.json({ error: error instanceof Error ? error.message : 'Send failed' }, { status });
  }
}
