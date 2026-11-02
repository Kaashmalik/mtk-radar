/**
 * Spreadsheet import: CSV/TSV parsing, header auto-mapping and row → lead
 * conversion. Pure functions shared by the import dialog (preview) and the
 * import API (validation), so both agree on what a row means.
 */

import {
  DEAL_STAGES,
  LEAD_STATUSES,
  normalizePhone,
  type DealStage,
  type Lead,
  type LeadStatus,
} from '@/lib/lead-types';

export type RawRow = Record<string, string>;

/** Lead fields an import may set, and the header names we recognise for each. */
export const IMPORT_FIELDS = {
  id: ['lead_id', 'id', 'place_id', 'google_place_id'],
  name: ['name', 'business_name', 'business', 'company', 'title', 'contact_name'],
  phone: ['phone_e164', 'phone', 'phone_number', 'mobile', 'whatsapp', 'whatsapp_number', 'contact_number', 'tel'],
  email: ['email', 'email_address', 'e-mail'],
  website: ['website', 'url', 'site', 'web'],
  business_type: ['business_type', 'category', 'type', 'industry', 'niche'],
  area: ['area', 'location', 'address', 'city', 'locality', 'neighborhood'],
  lead_score: ['lead_score', 'score'],
  lead_tier: ['lead_tier', 'tier', 'grade'],
  scenario: ['scenario'],
  rating: ['google_rating', 'rating', 'stars'],
  reviews: ['google_review_count', 'reviews', 'review_count', 'reviews_count'],
  google_maps_url: ['google_maps_url', 'maps_url', 'map_url', 'google_maps', 'maps_link'],
  recommended_pitch: ['recommended_pitch', 'pitch'],
  message: ['message', 'whatsapp_message', 'opener', 'first_message', 'draft'],
  status: ['status', 'lead_status', 'outreach_status'],
  notes: ['notes', 'note', 'comments'],
  tags: ['tags', 'labels'],
  next_followup: ['next_followup', 'follow_up', 'followup', 'next_follow_up'],
  last_contacted: ['last_contacted', 'contacted_on', 'sent_on', 'sent_date'],
  deal_stage: ['deal_stage', 'stage'],
  deal_value: ['deal_value', 'value', 'amount', 'budget'],
} as const;

export type ImportField = keyof typeof IMPORT_FIELDS;
export type ColumnMapping = Partial<Record<ImportField, string>>;

const MAX_IMPORT_ROWS = 10_000;

/** RFC 4180-ish parser. Detects tab vs comma from the header line. */
export function parseDelimited(text: string): RawRow[] {
  const clean = text.replace(/^﻿/, '');
  const firstLine = clean.slice(0, clean.indexOf('\n') === -1 ? undefined : clean.indexOf('\n'));
  const delimiter = (firstLine.match(/\t/g)?.length || 0) > (firstLine.match(/,/g)?.length || 0) ? '\t' : ',';

  const rows: string[][] = [];
  let row: string[] = [];
  let cell = '';
  let quoted = false;
  for (let i = 0; i < clean.length; i++) {
    const c = clean[i];
    if (quoted) {
      if (c === '"' && clean[i + 1] === '"') {
        cell += '"';
        i++;
      } else if (c === '"') quoted = false;
      else cell += c;
    } else if (c === '"' && cell === '') quoted = true;
    else if (c === delimiter) {
      row.push(cell);
      cell = '';
    } else if (c === '\n') {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = '';
    } else if (c !== '\r') cell += c;
  }
  if (cell || row.length) {
    row.push(cell);
    rows.push(row);
  }

  const header = (rows[0] || []).map((h) => h.trim());
  return rows
    .slice(1, MAX_IMPORT_ROWS + 1)
    .filter((cells) => cells.some((value) => value.trim()))
    .map((cells) => Object.fromEntries(header.map((key, i) => [key, (cells[i] ?? '').trim()])));
}

const headerKey = (value: string) => value.trim().toLowerCase().replace(/[\s.]+/g, '_');

/** Picks the best header for each field by name. */
export function autoMapColumns(headers: string[]): ColumnMapping {
  const byKey = new Map(headers.map((header) => [headerKey(header), header]));
  const mapping: ColumnMapping = {};
  for (const [field, aliases] of Object.entries(IMPORT_FIELDS) as [ImportField, readonly string[]][]) {
    const found = aliases.find((alias) => byKey.has(alias));
    if (found) mapping[field] = byKey.get(found);
  }
  return mapping;
}

function number(value: string | undefined): number | null {
  if (!value) return null;
  const parsed = Number(value.replace(/[^\d.-]/g, ''));
  return Number.isFinite(parsed) ? parsed : null;
}

function isoDate(value: string | undefined): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (/^\d{4}-\d{2}-\d{2}/.test(trimmed)) return trimmed.slice(0, 10);
  // dd/mm/yyyy — the common format in Pakistan and the UK.
  const dmy = trimmed.match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/);
  if (dmy) return `${dmy[3]}-${dmy[2].padStart(2, '0')}-${dmy[1].padStart(2, '0')}`;
  return null;
}

function status(value: string | undefined): LeadStatus | undefined {
  const key = (value || '').trim().toLowerCase().replace(/\s+/g, '_');
  if ((LEAD_STATUSES as string[]).includes(key)) return key as LeadStatus;
  if (key === 'sent') return 'contacted';
  if (key === 'not_on_whatsapp') return 'skipped';
  return undefined;
}

function dealStage(value: string | undefined): DealStage | undefined {
  const key = (value || '').trim().toLowerCase().replace(/\s+/g, '_');
  return (DEAL_STAGES as string[]).includes(key) ? (key as DealStage) : undefined;
}

/** The subset of lead fields a spreadsheet row provides. */
export type ImportedLead = Partial<Lead> & { name: string; phone: string };

export type RowResult = { lead: ImportedLead; error?: undefined } | { lead?: undefined; error: string };

export function rowToLead(row: RawRow, mapping: ColumnMapping): RowResult {
  const get = (field: ImportField) => {
    const column = mapping[field];
    return column ? (row[column] ?? '').trim() : '';
  };

  const name = get('name').slice(0, 200);
  const phone = normalizePhone(get('phone'));
  if (!name) return { error: 'Missing business name' };
  if (!phone && !get('email')) return { error: 'Needs a valid phone number or email' };

  const lead: ImportedLead = { name, phone };
  const text = (field: ImportField & keyof Lead, max = 500) => {
    const value = get(field);
    if (value) (lead as Record<string, unknown>)[field] = value.slice(0, max);
  };

  const id = get('id');
  if (id) lead.id = id.slice(0, 200);
  text('email', 200);
  text('website', 300);
  text('business_type', 120);
  text('area', 200);
  text('lead_tier', 4);
  text('scenario', 60);
  text('google_maps_url', 1000);
  text('recommended_pitch', 2000);
  text('message', 2000);
  text('notes', 4000);

  const score = number(get('lead_score'));
  if (score !== null) lead.lead_score = Math.round(Math.min(Math.max(score, 0), 100));
  const rating = number(get('rating'));
  if (rating !== null) lead.rating = Math.min(Math.max(rating, 0), 5);
  const reviews = number(get('reviews'));
  if (reviews !== null) lead.reviews = Math.max(0, Math.round(reviews));
  const value = number(get('deal_value'));
  if (value !== null) lead.deal_value = value;

  const parsedStatus = status(get('status'));
  if (parsedStatus) lead.status = parsedStatus;
  const parsedStage = dealStage(get('deal_stage'));
  if (parsedStage) lead.deal_stage = parsedStage;
  const followup = isoDate(get('next_followup'));
  if (followup) lead.next_followup = followup;
  const contacted = isoDate(get('last_contacted'));
  if (contacted) lead.last_contacted = contacted;

  const tags = get('tags');
  if (tags) {
    lead.tags = Array.from(
      new Set(
        tags
          .split(/[;,|]/)
          .map((tag) => tag.trim().toLowerCase())
          .filter(Boolean),
      ),
    ).slice(0, 12);
  }

  return { lead };
}

/**
 * Turns a Google Sheets link into its CSV export URL. Only docs.google.com
 * spreadsheet links are accepted, so the server never fetches arbitrary URLs.
 */
export function googleSheetCsvUrl(input: string): string | null {
  let url: URL;
  try {
    url = new URL(input.trim());
  } catch {
    return null;
  }
  if (url.protocol !== 'https:' || url.hostname !== 'docs.google.com') return null;
  const match = url.pathname.match(/^\/spreadsheets\/d\/([a-zA-Z0-9_-]{20,})/);
  if (!match) return null;
  const gid = url.searchParams.get('gid') || url.hash.match(/gid=(\d+)/)?.[1] || '0';
  return `https://docs.google.com/spreadsheets/d/${match[1]}/export?format=csv&gid=${encodeURIComponent(gid)}`;
}
