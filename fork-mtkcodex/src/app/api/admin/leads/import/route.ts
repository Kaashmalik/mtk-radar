import { NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/admin-auth';
import { IMPORT_FIELDS, rowToLead, type ColumnMapping, type ImportedLead, type RawRow } from '@/lib/lead-import';
import { LeadError, importLeads, type ImportStrategy } from '@/lib/leads';

export const dynamic = 'force-dynamic';

/** Rows per request. The dialog sends large sheets in chunks of this size. */
const MAX_ROWS = 1000;

export async function POST(req: Request) {
  const session = await requireAdmin(req);
  if (session instanceof Response) return session;

  let body: { rows?: unknown; mapping?: unknown; strategy?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  if (!Array.isArray(body.rows) || !body.rows.length) {
    return NextResponse.json({ error: 'No rows to import' }, { status: 422 });
  }
  if (body.rows.length > MAX_ROWS) {
    return NextResponse.json({ error: `Send at most ${MAX_ROWS} rows per request` }, { status: 413 });
  }

  // Only known fields, mapped to string column names.
  const mapping: ColumnMapping = {};
  const rawMapping = (body.mapping || {}) as Record<string, unknown>;
  for (const field of Object.keys(IMPORT_FIELDS) as (keyof typeof IMPORT_FIELDS)[]) {
    if (typeof rawMapping[field] === 'string' && rawMapping[field]) mapping[field] = rawMapping[field] as string;
  }
  if (!mapping.name || (!mapping.phone && !mapping.email)) {
    return NextResponse.json({ error: 'Map at least the name and a phone or email column' }, { status: 422 });
  }

  const strategy: ImportStrategy = body.strategy === 'merge' ? 'merge' : 'skip';
  const leads: ImportedLead[] = [];
  let invalid = 0;
  for (const row of body.rows) {
    if (!row || typeof row !== 'object') {
      invalid++;
      continue;
    }
    const cells = Object.fromEntries(
      Object.entries(row as Record<string, unknown>).map(([key, value]) => [key, value == null ? '' : String(value)]),
    ) as RawRow;
    const result = rowToLead(cells, mapping);
    if (result.lead) leads.push(result.lead);
    else invalid++;
  }

  try {
    const result = await importLeads(leads, strategy);
    return NextResponse.json({ ...result, invalid });
  } catch (error) {
    const status = error instanceof LeadError ? error.status : 500;
    return NextResponse.json({ error: error instanceof Error ? error.message : 'Import failed' }, { status });
  }
}
