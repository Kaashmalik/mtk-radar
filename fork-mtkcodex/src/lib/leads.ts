import { randomUUID } from 'node:crypto';
import { mutateTable, readTable } from '@/lib/file-store';
import { inList, supabase, supabaseConfigured } from '@/lib/supabase';
import {
  CONTACTED_STATUSES,
  DEAL_STAGES,
  DEAL_STAGE_LABELS,
  LEAD_STATUSES,
  STATUS_LABELS,
  WON_DEAL_STAGES,
  formatMoney,
  normalizePhone,
  phoneDigits,
  todayPKT,
  type ActivityKind,
  type DealStage,
  type Lead,
  type LeadActivity,
  type LeadSource,
  type LeadStatus,
} from '@/lib/lead-types';
import type { ImportedLead } from '@/lib/lead-import';

export type { Lead, LeadStatus, LeadActivity } from '@/lib/lead-types';
export { LEAD_STATUSES, STATUS_LABELS, leadStats, todayPKT, waLink, leadsToCsv } from '@/lib/lead-types';

export type StorageMode = 'supabase' | 'file' | 'readonly';

/** Serverless hosts have a read-only, throwaway filesystem, so local files can't be the store there. */
function serverlessHost(): boolean {
  return Boolean(process.env.VERCEL || process.env.NETLIFY || process.env.AWS_LAMBDA_FUNCTION_NAME);
}

export function storageMode(): StorageMode {
  if (supabaseConfigured()) return 'supabase';
  if (serverlessHost()) return 'readonly';
  return 'file';
}

const READONLY_ERROR = 'No database connected. Add SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to save CRM changes.';

/** A user-facing error (bad input, missing lead) as opposed to an outage. */
export class LeadError extends Error {
  constructor(
    message: string,
    readonly status = 400,
  ) {
    super(message);
  }
}

/* ---------------------------------------------------------------------------
 * Reads
 * ------------------------------------------------------------------------- */

/** PostgREST caps responses at 1,000 rows on Supabase, so page through. */
async function selectAll<T>(pathAndQuery: string, pageSize = 1000): Promise<T[]> {
  const rows: T[] = [];
  for (let offset = 0; ; offset += pageSize) {
    const page = await supabase<T[]>(`${pathAndQuery}&limit=${pageSize}&offset=${offset}`);
    rows.push(...page);
    if (page.length < pageSize) return rows;
  }
}

export async function listLeads(): Promise<{ leads: Lead[]; mode: StorageMode }> {
  const mode = storageMode();
  if (mode === 'supabase') {
    const leads = await selectAll<Lead>('leads?select=*&order=created_at.desc.nullslast,id.asc');
    return { leads, mode };
  }
  if (mode === 'readonly') return { leads: [], mode };
  return { leads: await readTable<Lead>('leads'), mode };
}

export async function getLead(id: string): Promise<Lead | null> {
  if (storageMode() === 'supabase') {
    const rows = await supabase<Lead[]>(`leads?id=eq.${encodeURIComponent(id)}&select=*`);
    return rows[0] || null;
  }
  const leads = await readTable<Lead>('leads');
  return leads.find((lead) => lead.id === id) || null;
}

export async function findLeadByPhone(raw: string): Promise<Lead | null> {
  const digits = phoneDigits(raw);
  if (!digits) return null;
  if (storageMode() === 'supabase') {
    const rows = await supabase<Lead[]>(
      `leads?or=${encodeURIComponent(`(phone.eq.+${digits},phone.eq.${digits})`)}&select=*&limit=1`,
    );
    return rows[0] || null;
  }
  const leads = await readTable<Lead>('leads');
  return leads.find((lead) => phoneDigits(lead.phone) === digits) || null;
}

export async function findLeadByEmail(email: string): Promise<Lead | null> {
  const needle = email.trim().toLowerCase();
  if (!needle) return null;
  if (storageMode() === 'supabase') {
    // ilike gives a case-insensitive match; escape its wildcards (`_` is common in emails).
    const pattern = needle.replace(/[\\%_]/g, '\\$&');
    const rows = await supabase<Lead[]>(`leads?email=ilike.${encodeURIComponent(pattern)}&select=*&limit=1`);
    return rows[0] || null;
  }
  const leads = await readTable<Lead>('leads');
  return leads.find((lead) => lead.email.toLowerCase() === needle) || null;
}

/* ---------------------------------------------------------------------------
 * Activity timeline
 * ------------------------------------------------------------------------- */

export type NewActivity = { lead_id: string; kind: ActivityKind; summary: string; meta?: Record<string, unknown> };

/**
 * Activity is history, not state: a failure to log must never undo or block
 * the CRM change that caused it, so errors are logged and swallowed.
 */
export async function addActivities(items: NewActivity[]): Promise<void> {
  if (!items.length || storageMode() === 'readonly') return;
  const rows = items.map((item) => ({ ...item, meta: item.meta || {}, summary: item.summary.slice(0, 500) }));
  try {
    if (storageMode() === 'supabase') {
      for (let i = 0; i < rows.length; i += 500) {
        await supabase('lead_activities', {
          method: 'POST',
          headers: { Prefer: 'return=minimal' },
          body: JSON.stringify(rows.slice(i, i + 500)),
        });
      }
      return;
    }
    await mutateTable<LeadActivity, void>('activities', (all) => {
      const now = new Date().toISOString();
      for (const row of rows) all.push({ id: randomUUID(), created_at: now, ...row });
    });
  } catch (error) {
    console.error('leads: could not record activity', error instanceof Error ? error.message : error);
  }
}

export async function listActivities(leadId: string, limit = 200): Promise<LeadActivity[]> {
  const mode = storageMode();
  if (mode === 'readonly') return [];
  if (mode === 'supabase') {
    return supabase<LeadActivity[]>(
      `lead_activities?lead_id=eq.${encodeURIComponent(leadId)}&select=*&order=created_at.desc&limit=${limit}`,
    );
  }
  const all = await readTable<LeadActivity>('activities');
  return all
    .filter((item) => item.lead_id === leadId)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, limit);
}

export type ActivityWithLead = LeadActivity & { lead_name: string };

/** Recent activity across all leads, newest first. */
export async function recentActivities(options: { since?: string; kinds?: ActivityKind[]; limit?: number } = {}) {
  const mode = storageMode();
  const limit = options.limit ?? 50;
  if (mode === 'readonly') return [] as ActivityWithLead[];
  if (mode === 'supabase') {
    const filters = [
      'select=*,leads(name)',
      'order=created_at.desc',
      `limit=${limit}`,
      options.since ? `created_at=gte.${encodeURIComponent(options.since)}` : '',
      options.kinds?.length ? `kind=${encodeURIComponent(inList(options.kinds))}` : '',
    ].filter(Boolean);
    const rows = await supabase<(LeadActivity & { leads: { name: string } | null })[]>(
      `lead_activities?${filters.join('&')}`,
    );
    return rows.map(({ leads, ...row }) => ({ ...row, lead_name: leads?.name || '' }));
  }
  const [all, leads] = await Promise.all([readTable<LeadActivity>('activities'), readTable<Lead>('leads')]);
  const names = new Map(leads.map((lead) => [lead.id, lead.name]));
  return all
    .filter((item) => (!options.since || item.created_at >= options.since) && (!options.kinds || options.kinds.includes(item.kind)))
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, limit)
    .map((item) => ({ ...item, lead_name: names.get(item.lead_id) || '' }));
}

/* ---------------------------------------------------------------------------
 * Writes
 * ------------------------------------------------------------------------- */

const PROFILE_FIELDS = [
  'name',
  'business_type',
  'area',
  'phone',
  'email',
  'website',
  'lead_score',
  'lead_tier',
  'scenario',
  'rating',
  'reviews',
  'google_maps_url',
  'recommended_pitch',
] as const;

export type LeadPatch = Partial<
  Pick<
    Lead,
    | 'status'
    | 'notes'
    | 'next_followup'
    | 'last_contacted'
    | 'do_not_contact'
    | 'message'
    | 'starred'
    | 'tags'
    | 'deal_stage'
    | 'deal_value'
    | 'deal_currency'
    | 'name'
    | 'business_type'
    | 'area'
    | 'phone'
    | 'email'
    | 'website'
  >
> & {
  /** Appends a dated line to notes and records it on the timeline. */
  append_note?: string;
};

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Validates an untrusted JSON body into a LeadPatch. Throws LeadError. */
export function parseLeadPatch(body: Record<string, unknown>): LeadPatch {
  const patch: LeadPatch = {};
  const str = (key: string, max: number) => {
    const value = body[key];
    if (value === undefined) return undefined;
    if (typeof value !== 'string') throw new LeadError(`${key} must be text`);
    return value.slice(0, max);
  };
  const date = (key: 'next_followup' | 'last_contacted') => {
    const value = body[key];
    if (value === undefined) return;
    if (value === null || value === '') patch[key] = null;
    else if (typeof value === 'string' && DATE_RE.test(value)) patch[key] = value;
    else throw new LeadError(`${key} must be a YYYY-MM-DD date`);
  };

  if (body.status !== undefined) {
    if (!(LEAD_STATUSES as unknown[]).includes(body.status)) throw new LeadError('Invalid status');
    patch.status = body.status as LeadStatus;
  }
  if (body.deal_stage !== undefined) {
    if (!(DEAL_STAGES as unknown[]).includes(body.deal_stage)) throw new LeadError('Invalid deal stage');
    patch.deal_stage = body.deal_stage as DealStage;
  }
  if (body.deal_value !== undefined) {
    if (body.deal_value === null || body.deal_value === '') patch.deal_value = null;
    else {
      const value = Number(body.deal_value);
      if (!Number.isFinite(value) || value < 0) throw new LeadError('Deal value must be a positive number');
      patch.deal_value = Math.round(value * 100) / 100;
    }
  }
  if (body.deal_currency !== undefined) {
    const value = str('deal_currency', 3)?.toUpperCase();
    if (!value || !/^[A-Z]{3}$/.test(value)) throw new LeadError('Currency must be a 3-letter code');
    patch.deal_currency = value;
  }
  if (body.do_not_contact !== undefined) {
    if (typeof body.do_not_contact !== 'boolean') throw new LeadError('do_not_contact must be true or false');
    patch.do_not_contact = body.do_not_contact;
  }
  if (body.starred !== undefined) {
    if (typeof body.starred !== 'boolean') throw new LeadError('starred must be true or false');
    patch.starred = body.starred;
  }
  if (body.tags !== undefined) {
    if (!Array.isArray(body.tags) || body.tags.some((tag) => typeof tag !== 'string')) {
      throw new LeadError('tags must be a list of text');
    }
    patch.tags = Array.from(
      new Set((body.tags as string[]).map((tag) => tag.trim().toLowerCase().slice(0, 30)).filter(Boolean)),
    ).slice(0, 12);
  }
  date('next_followup');
  date('last_contacted');

  const notes = str('notes', 4000);
  if (notes !== undefined) patch.notes = notes;
  const message = str('message', 2000);
  if (message !== undefined) patch.message = message;
  const appendNote = str('append_note', 1000)?.trim();
  if (appendNote) patch.append_note = appendNote;

  for (const [key, max] of [
    ['name', 200],
    ['business_type', 120],
    ['area', 200],
    ['email', 200],
    ['website', 300],
  ] as const) {
    const value = str(key, max);
    if (value !== undefined) patch[key] = value.trim();
  }
  if (patch.name !== undefined && !patch.name) throw new LeadError('Name cannot be empty');
  if (body.phone !== undefined) {
    const raw = str('phone', 40) || '';
    const phone = normalizePhone(raw);
    if (raw.trim() && !phone) throw new LeadError('Phone number is not valid');
    patch.phone = phone;
  }
  return patch;
}

type Change = { changes: Partial<Lead>; activities: NewActivity[] };

/** Works out the stored changes and timeline entries for one lead. */
export function planLeadChange(current: Lead, patch: LeadPatch, today = todayPKT()): Change {
  const changes: Partial<Lead> = {};
  const activities: NewActivity[] = [];
  const log = (kind: ActivityKind, summary: string, meta: Record<string, unknown> = {}) =>
    activities.push({ lead_id: current.id, kind, summary, meta });

  // Profile edits
  const edited: string[] = [];
  for (const key of ['name', 'business_type', 'area', 'phone', 'email', 'website'] as const) {
    if (patch[key] !== undefined && patch[key] !== current[key]) {
      changes[key] = patch[key] as string;
      edited.push(key.replace('_', ' '));
    }
  }
  if (edited.length) log('edit', `Updated ${edited.join(', ')}`);

  if (patch.message !== undefined && patch.message !== current.message) changes.message = patch.message;
  if (patch.notes !== undefined && patch.notes !== current.notes) changes.notes = patch.notes;
  if (patch.append_note) {
    const base = (changes.notes ?? current.notes ?? '').trim();
    changes.notes = [base, `[${today}] ${patch.append_note}`].filter(Boolean).join('\n').slice(-4000);
    log('note', patch.append_note);
  }
  if (patch.starred !== undefined && patch.starred !== Boolean(current.starred)) changes.starred = patch.starred;
  if (patch.tags !== undefined) changes.tags = patch.tags;

  // Deal stage drives the sales status forward, never backwards.
  let status = patch.status ?? current.status;
  const stage = patch.deal_stage ?? current.deal_stage ?? 'none';
  if (patch.deal_stage !== undefined && patch.deal_stage !== (current.deal_stage ?? 'none')) {
    changes.deal_stage = patch.deal_stage;
    log('deal', `Deal: ${DEAL_STAGE_LABELS[current.deal_stage ?? 'none']} → ${DEAL_STAGE_LABELS[patch.deal_stage]}`, {
      from: current.deal_stage ?? 'none',
      to: patch.deal_stage,
    });
    if (WON_DEAL_STAGES.includes(stage)) status = 'won';
    else if (['discovery', 'proposal', 'negotiation'].includes(stage) && ['new', 'queued', 'contacted', 'replied'].includes(status)) {
      status = 'interested';
    }
  }
  if (patch.deal_value !== undefined && patch.deal_value !== (current.deal_value ?? null)) {
    changes.deal_value = patch.deal_value;
    const currency = patch.deal_currency || current.deal_currency || 'PKR';
    log('deal', patch.deal_value === null ? 'Deal value cleared' : `Deal value set to ${formatMoney(patch.deal_value, currency)}`);
  }
  if (patch.deal_currency !== undefined && patch.deal_currency !== current.deal_currency) {
    changes.deal_currency = patch.deal_currency;
  }

  // Opt-out is enforced on the server, not just hidden in the UI.
  const doNotContact = patch.do_not_contact ?? current.do_not_contact;
  if (patch.do_not_contact !== undefined && patch.do_not_contact !== current.do_not_contact) {
    changes.do_not_contact = patch.do_not_contact;
    log('opt_out', patch.do_not_contact ? 'Marked do-not-contact' : 'Do-not-contact removed');
  }
  if (doNotContact && status === 'queued') {
    throw new LeadError('This lead is marked do-not-contact, so it cannot be queued for outreach.', 409);
  }

  if (status !== current.status) {
    changes.status = status;
    log('status', `Status: ${STATUS_LABELS[current.status]} → ${STATUS_LABELS[status]}`, { from: current.status, to: status });
    const firstTouch = status === 'contacted' && !CONTACTED_STATUSES.includes(current.status);
    if (firstTouch) {
      if (doNotContact) throw new LeadError('This lead is marked do-not-contact.', 409);
      log('message_out', 'First WhatsApp message sent', { channel: 'whatsapp', manual: true });
      if (patch.last_contacted === undefined) changes.last_contacted = today;
    }
  }

  if (patch.last_contacted !== undefined && patch.last_contacted !== current.last_contacted) {
    changes.last_contacted = patch.last_contacted;
  }
  if (patch.next_followup !== undefined && patch.next_followup !== current.next_followup) {
    changes.next_followup = patch.next_followup;
    log('followup', patch.next_followup ? `Follow-up set for ${patch.next_followup}` : 'Follow-up cleared');
  }

  return { changes, activities };
}

/** Low-level write with no business rules or timeline entries. */
export async function writeLeadChanges(id: string, changes: Partial<Lead>): Promise<Lead> {
  const stamped = { ...changes, updated_at: new Date().toISOString() };
  if (storageMode() === 'supabase') {
    const rows = await supabase<Lead[]>(`leads?id=eq.${encodeURIComponent(id)}&select=*`, {
      method: 'PATCH',
      headers: { Prefer: 'return=representation' },
      body: JSON.stringify(stamped),
    });
    if (!rows[0]) throw new LeadError('Lead not found', 404);
    return rows[0];
  }
  return mutateTable<Lead, Lead>('leads', (leads) => {
    const index = leads.findIndex((lead) => lead.id === id);
    if (index === -1) throw new LeadError('Lead not found', 404);
    const next = { ...leads[index], ...stamped };
    // Mirrors the first_contacted trigger from migration 0003.
    if (!next.first_contacted && next.last_contacted) next.first_contacted = next.last_contacted;
    leads[index] = next;
    return next;
  });
}

export async function updateLead(id: string, patch: LeadPatch): Promise<Lead> {
  if (storageMode() === 'readonly') throw new LeadError(READONLY_ERROR, 503);
  const current = await getLead(id);
  if (!current) throw new LeadError('Lead not found', 404);
  const { changes, activities } = planLeadChange(current, patch);
  if (!Object.keys(changes).length) return current;
  const lead = await writeLeadChanges(id, changes);
  await addActivities(activities);
  return lead;
}

/** Applies the same patch to many leads; returns the updated rows and per-lead errors. */
export async function bulkUpdateLeads(ids: string[], patch: LeadPatch) {
  const updated: Lead[] = [];
  const errors: { id: string; error: string }[] = [];
  // Small concurrency keeps PostgREST happy without a slow serial loop.
  const queue = [...new Set(ids)].slice(0, 500);
  async function worker() {
    for (let id = queue.shift(); id !== undefined; id = queue.shift()) {
      try {
        updated.push(await updateLead(id, patch));
      } catch (error) {
        errors.push({ id, error: error instanceof Error ? error.message : 'Update failed' });
      }
    }
  }
  await Promise.all(Array.from({ length: 6 }, worker));
  return { updated, errors };
}

export async function deleteLeads(ids: string[]): Promise<number> {
  const mode = storageMode();
  if (mode === 'readonly') throw new LeadError(READONLY_ERROR, 503);
  const unique = [...new Set(ids)].slice(0, 500);
  if (!unique.length) return 0;
  if (mode === 'supabase') {
    // Erase conversations too (erasure requests); activities cascade with the lead.
    const filter = encodeURIComponent(inList(unique));
    await supabase(`messages?lead_id=${filter}`, { method: 'DELETE' });
    await supabase(`chat_sessions?lead_id=${filter}`, { method: 'DELETE' });
    const rows = await supabase<{ id: string }[]>(`leads?id=${filter}&select=id`, {
      method: 'DELETE',
      headers: { Prefer: 'return=representation' },
    });
    return rows.length;
  }
  const set = new Set(unique);
  const removed = await mutateTable<Lead, number>('leads', (leads) => {
    const before = leads.length;
    const kept = leads.filter((lead) => !set.has(lead.id));
    leads.splice(0, leads.length, ...kept);
    return before - kept.length;
  });
  for (const table of ['activities', 'messages', 'chats'] as const) {
    await mutateTable<{ lead_id: string | null }, void>(table, (all) => {
      const kept = all.filter((item) => !item.lead_id || !set.has(item.lead_id));
      all.splice(0, all.length, ...kept);
    });
  }
  return removed;
}

export function blankLead(input: Partial<Lead> & { name: string }, source: LeadSource): Lead {
  const now = new Date().toISOString();
  return {
    id: input.id || `${source}:${randomUUID()}`,
    name: input.name,
    business_type: input.business_type || '',
    area: input.area || '',
    phone: input.phone || '',
    email: input.email || '',
    website: input.website || '',
    lead_score: input.lead_score ?? 0,
    lead_tier: input.lead_tier || 'C',
    scenario: input.scenario || '',
    rating: input.rating ?? null,
    reviews: input.reviews ?? null,
    google_maps_url: input.google_maps_url || '',
    recommended_pitch: input.recommended_pitch || '',
    message: input.message || '',
    status: input.status || 'new',
    channel: input.channel || 'whatsapp',
    notes: input.notes || '',
    last_contacted: input.last_contacted ?? null,
    first_contacted: input.last_contacted ?? null,
    next_followup: input.next_followup ?? null,
    do_not_contact: input.do_not_contact ?? false,
    source,
    starred: input.starred ?? false,
    tags: input.tags || [],
    deal_stage: input.deal_stage || 'none',
    deal_value: input.deal_value ?? null,
    deal_currency: input.deal_currency || 'PKR',
    last_inbound_at: input.last_inbound_at ?? null,
    last_outbound_at: input.last_outbound_at ?? null,
    unread_count: input.unread_count ?? 0,
    city: input.city || '',
    region: input.region || '',
    country: input.country || '',
    timezone: input.timezone || '',
    preferred_channel: input.preferred_channel || '',
    contact_token: input.contact_token ?? null,
    created_at: now,
    updated_at: now,
  };
}

async function insertLeads(leads: Lead[]): Promise<void> {
  if (!leads.length) return;
  if (storageMode() === 'supabase') {
    for (let i = 0; i < leads.length; i += 500) {
      await supabase('leads?on_conflict=id', {
        method: 'POST',
        headers: { Prefer: 'resolution=ignore-duplicates,return=minimal' },
        body: JSON.stringify(leads.slice(i, i + 500)),
      });
    }
    return;
  }
  await mutateTable<Lead, void>('leads', (rows) => {
    const ids = new Set(rows.map((lead) => lead.id));
    for (const lead of leads) if (!ids.has(lead.id)) rows.unshift(lead);
  });
}

export async function createLead(input: Partial<Lead> & { name: string }, source: LeadSource, summary: string): Promise<Lead> {
  if (storageMode() === 'readonly') throw new LeadError(READONLY_ERROR, 503);
  const name = input.name.trim().slice(0, 200);
  if (!name) throw new LeadError('Name is required');
  const phone = input.phone ? normalizePhone(input.phone) : '';
  if (input.phone && !phone) throw new LeadError('Phone number is not valid');
  if (phone) {
    const existing = await findLeadByPhone(phone);
    if (existing) throw new LeadError(`${existing.name} already uses this phone number.`, 409);
  }
  const lead = blankLead({ ...input, name, phone }, source);
  await insertLeads([lead]);
  await addActivities([{ lead_id: lead.id, kind: 'created', summary }]);
  return lead;
}

export type ImportStrategy = 'skip' | 'merge';
export type ImportResult = { inserted: number; updated: number; skipped: number; duplicates: number };

/**
 * Adds spreadsheet rows to the CRM. Leads are matched by id, then phone, then
 * email. `skip` leaves matches alone; `merge` refreshes their profile fields
 * (name, area, score…) but never overwrites live CRM state such as status or
 * notes, except promoting a still-`new` lead to the imported status.
 */
export async function importLeads(rows: ImportedLead[], strategy: ImportStrategy): Promise<ImportResult> {
  if (storageMode() === 'readonly') throw new LeadError(READONLY_ERROR, 503);
  const { leads: existing } = await listLeads();
  const byId = new Map(existing.map((lead) => [lead.id, lead]));
  const byPhone = new Map(existing.filter((lead) => lead.phone).map((lead) => [phoneDigits(lead.phone), lead]));
  const byEmail = new Map(existing.filter((lead) => lead.email).map((lead) => [lead.email.toLowerCase(), lead]));

  const inserts: Lead[] = [];
  const updates: { id: string; changes: Partial<Lead> }[] = [];
  const seen = new Set<string>();
  const result: ImportResult = { inserted: 0, updated: 0, skipped: 0, duplicates: 0 };

  for (const row of rows) {
    const key = row.id || phoneDigits(row.phone) || row.email?.toLowerCase() || '';
    if (!key || seen.has(key)) {
      result.duplicates++;
      continue;
    }
    seen.add(key);

    const match =
      (row.id && byId.get(row.id)) ||
      (row.phone && byPhone.get(phoneDigits(row.phone))) ||
      (row.email && byEmail.get(row.email.toLowerCase())) ||
      null;

    if (!match) {
      const lead = blankLead(row, 'import');
      inserts.push(lead);
      continue;
    }
    if (strategy === 'skip') {
      result.skipped++;
      continue;
    }

    const changes: Partial<Lead> = {};
    for (const field of PROFILE_FIELDS) {
      const value = row[field];
      if (value !== undefined && value !== '' && value !== match[field]) {
        (changes as Record<string, unknown>)[field] = value;
      }
    }
    if (row.message && !match.message) changes.message = row.message;
    if (row.tags?.length) changes.tags = Array.from(new Set([...(match.tags || []), ...row.tags])).slice(0, 12);
    if (row.status && match.status === 'new' && row.status !== 'new') changes.status = row.status;
    if (row.next_followup && !match.next_followup) changes.next_followup = row.next_followup;

    if (Object.keys(changes).length) updates.push({ id: match.id, changes });
    else result.skipped++;
  }

  await insertLeads(inserts);
  result.inserted = inserts.length;

  // Updates run with a little concurrency; each is a single-row PATCH.
  const queue = [...updates];
  await Promise.all(
    Array.from({ length: 6 }, async () => {
      for (let item = queue.shift(); item; item = queue.shift()) {
        await writeLeadChanges(item.id, item.changes);
        result.updated++;
      }
    }),
  );

  await addActivities([
    ...inserts.map((lead) => ({ lead_id: lead.id, kind: 'import' as const, summary: 'Imported from spreadsheet' })),
    ...updates.map((item) => ({
      lead_id: item.id,
      kind: 'import' as const,
      summary: `Spreadsheet import updated ${Object.keys(item.changes).join(', ').replace(/_/g, ' ')}`,
    })),
  ]);

  return result;
}
