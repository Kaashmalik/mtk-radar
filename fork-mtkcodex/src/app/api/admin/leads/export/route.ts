import { requireAdmin } from '@/lib/admin-auth';
import { leadsToCsv, listLeads, todayPKT } from '@/lib/leads';

export const dynamic = 'force-dynamic';

export async function GET(req: Request) {
  const session = await requireAdmin(req);
  if (session instanceof Response) return session;

  const { leads } = await listLeads();
  return new Response(leadsToCsv(leads), {
    headers: {
      'Content-Type': 'text/csv; charset=utf-8',
      'Content-Disposition': `attachment; filename="mtk-leads-${todayPKT()}.csv"`,
      'Cache-Control': 'no-store',
    },
  });
}
