import { NextResponse } from 'next/server';
import { getAdminSession } from '@/lib/admin-auth';
import { analyticsEnabled, getAnalyticsSummary } from '@/lib/analytics';

export const dynamic = 'force-dynamic';

export async function GET() {
  const session = await getAdminSession();
  if (!session) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  if (!analyticsEnabled()) {
    return NextResponse.json({ summary: null, configured: false });
  }

  try {
    const summary = await getAnalyticsSummary();
    return NextResponse.json({ summary, configured: true });
  } catch (error) {
    return NextResponse.json(
      {
        summary: null,
        configured: true,
        error: error instanceof Error ? error.message : 'Could not load analytics',
      },
      { status: 500 },
    );
  }
}
