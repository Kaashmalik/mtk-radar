import { NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/admin-auth';
import {
  LeadError,
  bulkUpdateLeads,
  createLead,
  deleteLeads,
  leadStats,
  listLeads,
  parseLeadPatch,
  updateLead,
} from '@/lib/leads';

export const dynamic = 'force-dynamic';

function failure(error: unknown, fallback: string) {
  if (error instanceof LeadError) return NextResponse.json({ error: error.message }, { status: error.status });
  console.error(`admin/leads: ${fallback}`, error instanceof Error ? error.message : error);
  return NextResponse.json({ error: error instanceof Error ? error.message : fallback }, { status: 500 });
}

async function readBody(req: Request): Promise<Record<string, unknown> | null> {
  try {
    const body = await req.json();
    return body && typeof body === 'object' && !Array.isArray(body) ? (body as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

const idList = (value: unknown) =>
  Array.isArray(value) ? value.filter((id): id is string => typeof id === 'string' && Boolean(id.trim())) : [];

export async function GET(req: Request) {
  const session = await requireAdmin(req);
  if (session instanceof Response) return session;

  try {
    const { leads, mode } = await listLeads();
    return NextResponse.json({ leads, stats: leadStats(leads), mode, email: session.email });
  } catch (error) {
    return failure(error, 'Failed to load leads');
  }
}

/** Create one lead by hand. */
export async function POST(req: Request) {
  const session = await requireAdmin(req);
  if (session instanceof Response) return session;
  const body = await readBody(req);
  if (!body) return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });

  try {
    const patch = parseLeadPatch(body);
    if (!patch.name) throw new LeadError('Business name is required');
    if (!patch.phone && !patch.email) throw new LeadError('Add a phone number or an email');
    const { append_note, ...fields } = patch;
    const lead = await createLead(
      { ...fields, name: patch.name, notes: append_note || fields.notes || '' },
      'manual',
      'Added by hand',
    );
    return NextResponse.json({ lead }, { status: 201 });
  } catch (error) {
    return failure(error, 'Failed to create lead');
  }
}

/** Update one lead (`id`) or many (`ids`) with the same patch. */
export async function PATCH(req: Request) {
  const session = await requireAdmin(req);
  if (session instanceof Response) return session;
  const body = await readBody(req);
  if (!body) return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });

  try {
    const { id, ids, ...rest } = body;
    const patch = parseLeadPatch(rest);
    if (!Object.keys(patch).length) throw new LeadError('Nothing to update', 422);

    const many = idList(ids);
    if (many.length) {
      const result = await bulkUpdateLeads(many, patch);
      return NextResponse.json(result);
    }
    if (typeof id !== 'string' || !id.trim()) throw new LeadError('Lead id is required', 422);
    const lead = await updateLead(id.trim(), patch);
    return NextResponse.json({ lead });
  } catch (error) {
    return failure(error, 'Failed to update lead');
  }
}

export async function DELETE(req: Request) {
  const session = await requireAdmin(req);
  if (session instanceof Response) return session;
  const body = await readBody(req);
  const ids = idList(body?.ids);
  if (!ids.length) return NextResponse.json({ error: 'No leads selected' }, { status: 422 });

  try {
    const deleted = await deleteLeads(ids);
    return NextResponse.json({ deleted });
  } catch (error) {
    return failure(error, 'Failed to delete leads');
  }
}
