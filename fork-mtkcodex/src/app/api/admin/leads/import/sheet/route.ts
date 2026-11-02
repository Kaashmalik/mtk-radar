import { NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/admin-auth';
import { googleSheetCsvUrl, parseDelimited } from '@/lib/lead-import';

export const dynamic = 'force-dynamic';

const MAX_BYTES = 8 * 1024 * 1024;

/**
 * Fetches a Google Sheet as CSV and returns parsed rows for the import
 * preview. The sheet must be shared as "Anyone with the link can view".
 * Only docs.google.com spreadsheet URLs are fetched.
 */
export async function POST(req: Request) {
  const session = await requireAdmin(req);
  if (session instanceof Response) return session;

  let url = '';
  try {
    url = String(((await req.json()) as { url?: unknown }).url || '');
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const csvUrl = googleSheetCsvUrl(url);
  if (!csvUrl) {
    return NextResponse.json({ error: 'Paste a Google Sheets link (docs.google.com/spreadsheets/…)' }, { status: 422 });
  }

  try {
    // Google redirects the export to googleusercontent.com; refuse anything else.
    const res = await fetch(csvUrl, { cache: 'no-store', redirect: 'follow', signal: AbortSignal.timeout(20_000) });
    const finalHost = new URL(res.url).hostname;
    if (finalHost !== 'docs.google.com' && !finalHost.endsWith('.googleusercontent.com')) {
      return NextResponse.json({ error: 'Unexpected redirect from Google' }, { status: 502 });
    }
    const type = res.headers.get('content-type') || '';
    if (!res.ok || type.includes('text/html')) {
      return NextResponse.json(
        { error: 'Could not read the sheet. Share it as "Anyone with the link can view", or download it as CSV and upload the file.' },
        { status: 422 },
      );
    }
    const text = await res.text();
    if (text.length > MAX_BYTES) return NextResponse.json({ error: 'Sheet is too large (8 MB max)' }, { status: 413 });
    const rows = parseDelimited(text);
    return NextResponse.json({ rows, headers: rows[0] ? Object.keys(rows[0]) : [] });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? `Could not fetch the sheet: ${error.message}` : 'Could not fetch the sheet' },
      { status: 502 },
    );
  }
}
