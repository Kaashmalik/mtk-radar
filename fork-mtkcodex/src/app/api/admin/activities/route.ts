import { NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/admin-auth';
import { listActivities, recentActivities } from '@/lib/leads';

export const dynamic = 'force-dynamic';

/** `?lead=<id>` for one lead's timeline, otherwise the latest activity feed. */
export async function GET(req: Request) {
  const session = await requireAdmin(req);
  if (session instanceof Response) return session;

  const lead = new URL(req.url).searchParams.get('lead');
  try {
    const activities = lead ? await listActivities(lead) : await recentActivities({ limit: 40 });
    return NextResponse.json({ activities });
  } catch (error) {
    // Missing migration 0004 shows up here; the rest of the CRM keeps working.
    return NextResponse.json(
      { activities: [], error: error instanceof Error ? error.message : 'Could not load activity' },
      { status: 200 },
    );
  }
}
