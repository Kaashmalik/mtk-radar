/**
 * Lead CRM types and pure helpers. Safe to import from client and server code.
 */

export type LeadStatus = 'new' | 'queued' | 'contacted' | 'replied' | 'interested' | 'won' | 'lost' | 'skipped';

export const LEAD_STATUSES: LeadStatus[] = [
  'new',
  'queued',
  'contacted',
  'replied',
  'interested',
  'won',
  'lost',
  'skipped',
];

export const STATUS_LABELS: Record<LeadStatus, string> = {
  new: 'New',
  queued: 'Queued',
  contacted: 'Contacted',
  replied: 'Replied',
  interested: 'Interested',
  won: 'Won',
  lost: 'Lost',
  skipped: 'Not on WhatsApp',
};

/** Statuses that mean a first message has gone out. */
export const CONTACTED_STATUSES: LeadStatus[] = ['contacted', 'replied', 'interested', 'won', 'lost'];

export type DealStage =
  | 'none'
  | 'discovery'
  | 'proposal'
  | 'negotiation'
  | 'in_progress'
  | 'review'
  | 'delivered'
  | 'on_hold';

export const DEAL_STAGES: DealStage[] = [
  'none',
  'discovery',
  'proposal',
  'negotiation',
  'in_progress',
  'review',
  'delivered',
  'on_hold',
];

export const DEAL_STAGE_LABELS: Record<DealStage, string> = {
  none: 'No deal',
  discovery: 'Discovery call',
  proposal: 'Proposal sent',
  negotiation: 'Negotiation',
  in_progress: 'Work in progress',
  review: 'Client review',
  delivered: 'Delivered',
  on_hold: 'On hold',
};

/** Stages where the client has committed, so the lead counts as won. */
export const WON_DEAL_STAGES: DealStage[] = ['in_progress', 'review', 'delivered'];

export type LeadSource = 'scraper' | 'import' | 'manual' | 'website' | 'whatsapp' | 'web_chat' | 'email';

/** How a client prefers to be contacted (set on the contact form or in the chat). */
export type PreferredChannel = '' | 'email' | 'whatsapp' | 'call' | 'chat';

export const PREFERRED_CHANNEL_LABELS: Record<PreferredChannel, string> = {
  '': 'Not set',
  email: 'Email',
  whatsapp: 'WhatsApp',
  call: 'Phone / video call',
  chat: 'Live chat',
};

export type Lead = {
  id: string;
  name: string;
  business_type: string;
  area: string;
  phone: string;
  email: string;
  website: string;
  lead_score: number;
  lead_tier: string;
  scenario: string;
  rating: number | null;
  reviews: number | null;
  google_maps_url: string;
  recommended_pitch: string;
  message: string;
  status: LeadStatus;
  channel: string;
  notes: string;
  last_contacted: string | null;
  /** Stamped once, the first time the lead got a contact date. */
  first_contacted?: string | null;
  next_followup: string | null;
  do_not_contact: boolean;
  source?: LeadSource | string;
  starred?: boolean;
  tags?: string[];
  deal_stage?: DealStage;
  deal_value?: number | null;
  deal_currency?: string;
  last_inbound_at?: string | null;
  last_outbound_at?: string | null;
  unread_count?: number;
  city?: string;
  region?: string;
  country?: string;
  timezone?: string;
  preferred_channel?: PreferredChannel | string;
  contact_token?: string | null;
  created_at: string;
  updated_at: string;
};

export type ActivityKind =
  | 'created'
  | 'import'
  | 'status'
  | 'note'
  | 'followup'
  | 'deal'
  | 'message_out'
  | 'message_in'
  | 'opt_out'
  | 'edit';

export type LeadActivity = {
  id: number | string;
  lead_id: string;
  kind: ActivityKind;
  summary: string;
  meta: Record<string, unknown>;
  created_at: string;
};

export type Channel = 'web' | 'whatsapp' | 'email';

export const CHANNEL_LABELS: Record<Channel, string> = {
  web: 'Live chat',
  whatsapp: 'WhatsApp',
  email: 'Email',
};

/** One message on any channel. `thread_key` is 'web:<session>', 'wa:<digits>' or 'email:<address>'. */
export type Message = {
  id: number | string;
  lead_id: string | null;
  channel: Channel;
  thread_key: string;
  direction: 'in' | 'out';
  sender: '' | 'customer' | 'agent' | 'bot';
  msg_type: string;
  subject: string;
  body: string;
  external_id: string | null;
  status: 'received' | 'sent' | 'delivered' | 'read' | 'failed';
  error: string;
  meta: Record<string, unknown>;
  created_at: string;
};

/** Where a visitor or lead is, from Vercel's edge geolocation (city level only). */
export type Place = { city: string; region: string; country: string; timezone: string };

export type Conversation = {
  key: string;
  channel: Channel;
  lead_id: string | null;
  name: string;
  subtitle: string;
  last_body: string;
  last_direction: 'in' | 'out';
  last_at: string;
  last_inbound_at: string | null;
  unread: number;
  do_not_contact: boolean;
  status: LeadStatus | null;
  /** Live chat only: the visitor has the widget open right now. */
  online?: boolean;
  place?: Place;
};

export function threadChannel(key: string): Channel | null {
  if (key.startsWith('web:')) return 'web';
  if (key.startsWith('wa:')) return 'whatsapp';
  if (key.startsWith('email:')) return 'email';
  return null;
}

const todayDateFormatter = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Karachi',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

/** Today's date (YYYY-MM-DD) in the owner's timezone, Asia/Karachi. */
export function todayPKT(date: Date = new Date()): string {
  return todayDateFormatter.format(date);
}

/** YYYY-MM-DD in Asia/Karachi, `days` from the given date. */
export function addDaysPKT(days: number, from: Date = new Date()): string {
  return todayPKT(new Date(from.getTime() + days * 86_400_000));
}

/** WhatsApp only allows free-form replies within 24 hours of the customer's last message. */
export const WA_SESSION_MS = 24 * 60 * 60 * 1000;

export function waWindowOpen(lastInboundAt: string | null | undefined, now = Date.now()): boolean {
  if (!lastInboundAt) return false;
  return now - new Date(lastInboundAt).getTime() < WA_SESSION_MS;
}

/** "Active now" means the customer wrote in the last five minutes. */
export function customerActive(lastInboundAt: string | null | undefined, now = Date.now()): boolean {
  if (!lastInboundAt) return false;
  return now - new Date(lastInboundAt).getTime() < 5 * 60 * 1000;
}

/**
 * Normalises a phone number to E.164 (`+923001234567`). Local Pakistani
 * numbers (`0300…`) get the 92 country code. Returns '' when nothing usable.
 */
export function normalizePhone(raw: string | null | undefined, defaultCountry = '92'): string {
  let digits = String(raw ?? '').replace(/\D/g, '');
  if (!digits) return '';
  if (digits.startsWith('00')) digits = digits.slice(2);
  else if (digits.startsWith('0')) digits = defaultCountry + digits.slice(1);
  else if (digits.length === 10 && digits.startsWith('3') && defaultCountry === '92') digits = `92${digits}`;
  if (digits.length < 8 || digits.length > 15) return '';
  return `+${digits}`;
}

/** Digits only, as WhatsApp uses for `wa_id`. */
export function phoneDigits(raw: string | null | undefined): string {
  return normalizePhone(raw).replace(/^\+/, '');
}

export function leadStats(leads: Lead[]) {
  const byStatus = Object.fromEntries(LEAD_STATUSES.map((status) => [status, 0])) as Record<LeadStatus, number>;
  for (const lead of leads) byStatus[lead.status] = (byStatus[lead.status] || 0) + 1;
  const today = todayPKT();
  const contacted = leads.filter((lead) => CONTACTED_STATUSES.includes(lead.status)).length;
  const responded = (byStatus.replied || 0) + (byStatus.interested || 0) + (byStatus.won || 0);
  const openDeals = leads.filter(
    (lead) => lead.deal_stage && lead.deal_stage !== 'none' && lead.deal_stage !== 'delivered',
  );
  return {
    total: leads.length,
    byStatus,
    dueToday: leads.filter(
      (lead) =>
        lead.next_followup &&
        lead.next_followup <= today &&
        lead.status !== 'won' &&
        lead.status !== 'lost' &&
        !lead.do_not_contact,
    ).length,
    queued: leads.filter((lead) => lead.status === 'queued' && !lead.do_not_contact).length,
    won: byStatus.won || 0,
    contacted,
    responded,
    replyRate: contacted ? Math.round((responded / contacted) * 100) : 0,
    starred: leads.filter((lead) => lead.starred).length,
    unread: leads.reduce((sum, lead) => sum + (lead.unread_count || 0), 0),
    openDeals: openDeals.length,
    pipelineValue: openDeals.reduce((sum, lead) => sum + (Number(lead.deal_value) || 0), 0),
    wonValue: leads
      .filter((lead) => lead.deal_stage && WON_DEAL_STAGES.includes(lead.deal_stage))
      .reduce((sum, lead) => sum + (Number(lead.deal_value) || 0), 0),
  };
}

export function waLink(lead: Pick<Lead, 'phone' | 'message'>): string {
  const digits = lead.phone.replace(/\D/g, '');
  const text = lead.message?.trim() ? `?text=${encodeURIComponent(lead.message)}` : '';
  return `https://wa.me/${digits}${text}`;
}

/** Whether the UI may offer a chat/send action for this lead. */
export function canMessage(lead: Pick<Lead, 'phone' | 'do_not_contact'>): boolean {
  return Boolean(lead.phone) && !lead.do_not_contact;
}

export function formatMoney(value: number, currency = 'PKR'): string {
  try {
    return new Intl.NumberFormat('en-PK', { style: 'currency', currency, maximumFractionDigits: 0 }).format(value);
  } catch {
    return `${currency} ${Math.round(value).toLocaleString('en-PK')}`;
  }
}

const CSV_COLUMNS: { key: keyof Lead; label: string }[] = [
  { key: 'id', label: 'lead_id' },
  { key: 'name', label: 'name' },
  { key: 'business_type', label: 'business_type' },
  { key: 'area', label: 'area' },
  { key: 'phone', label: 'phone_e164' },
  { key: 'email', label: 'email' },
  { key: 'website', label: 'website' },
  { key: 'lead_score', label: 'lead_score' },
  { key: 'lead_tier', label: 'lead_tier' },
  { key: 'scenario', label: 'scenario' },
  { key: 'rating', label: 'google_rating' },
  { key: 'reviews', label: 'google_review_count' },
  { key: 'status', label: 'status' },
  { key: 'source', label: 'source' },
  { key: 'starred', label: 'starred' },
  { key: 'tags', label: 'tags' },
  { key: 'deal_stage', label: 'deal_stage' },
  { key: 'deal_value', label: 'deal_value' },
  { key: 'deal_currency', label: 'deal_currency' },
  { key: 'channel', label: 'channel' },
  { key: 'first_contacted', label: 'first_contacted' },
  { key: 'last_contacted', label: 'last_contacted' },
  { key: 'next_followup', label: 'next_followup' },
  { key: 'last_inbound_at', label: 'last_reply_at' },
  { key: 'do_not_contact', label: 'do_not_contact' },
  { key: 'notes', label: 'notes' },
  { key: 'message', label: 'message' },
  { key: 'recommended_pitch', label: 'recommended_pitch' },
  { key: 'google_maps_url', label: 'google_maps_url' },
  { key: 'created_at', label: 'created_at' },
  { key: 'updated_at', label: 'updated_at' },
];

/**
 * Spreadsheet apps execute cells that start with = + - @ (CSV injection).
 * Scraped business names are untrusted, so neutralise those with a leading
 * apostrophe. Plain phone numbers and negative numbers are left alone.
 */
export function csvCell(value: unknown): string {
  let text = value === null || value === undefined ? '' : Array.isArray(value) ? value.join('; ') : String(value);
  if (/^[=@\t\r]/.test(text) || (/^[+-]/.test(text) && !/^[+-][\d\s().-]*$/.test(text))) {
    text = `'${text}`;
  }
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function leadsToCsv(leads: Lead[]): string {
  const header = CSV_COLUMNS.map((column) => column.label).join(',');
  const rows = leads.map((lead) => CSV_COLUMNS.map((column) => csvCell(lead[column.key])).join(','));
  return `﻿${[header, ...rows].join('\r\n')}\r\n`;
}

export function statusTone(status: LeadStatus): string {
  switch (status) {
    case 'won':
      return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400';
    case 'interested':
    case 'replied':
      return 'border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400';
    case 'contacted':
    case 'queued':
      return 'border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400';
    case 'lost':
      return 'border-line bg-muted text-fg-subtle';
    case 'skipped':
      return 'border-line bg-muted text-fg-muted';
    default:
      return 'border-brand/30 bg-brand-soft text-brand';
  }
}

export function dealTone(stage: DealStage | undefined): string {
  switch (stage) {
    case 'delivered':
      return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400';
    case 'in_progress':
    case 'review':
      return 'border-violet-500/30 bg-violet-500/10 text-violet-600 dark:text-violet-400';
    case 'proposal':
    case 'negotiation':
    case 'discovery':
      return 'border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400';
    case 'on_hold':
      return 'border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400';
    default:
      return 'border-line bg-muted text-fg-subtle';
  }
}

/** "5m ago", "3h ago", "2d ago" — compact relative time for lists. */
export function timeAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return '—';
  const diff = Math.max(0, now - new Date(iso).getTime());
  const minutes = Math.round(diff / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString('en-PK', { day: 'numeric', month: 'short' });
}

/** "Lahore, Punjab, Pakistan" from a place, skipping blanks. */
export function placeLabel(place: Partial<Place> | null | undefined): string {
  if (!place) return '';
  const country = countryName(place.country || '');
  return [place.city, regionName(place.country || '', place.region || ''), country].filter(Boolean).join(', ');
}

let countryNames: Intl.DisplayNames | null = null;
export function countryName(code: string): string {
  if (!code || code.length !== 2) return code;
  try {
    countryNames ??= new Intl.DisplayNames(['en'], { type: 'region' });
    return countryNames.of(code.toUpperCase()) || code;
  } catch {
    return code;
  }
}

/** Region codes Vercel sends (ISO 3166-2 suffix) for the markets we serve most. */
const REGION_NAMES: Record<string, Record<string, string>> = {
  PK: { PB: 'Punjab', SD: 'Sindh', KP: 'Khyber Pakhtunkhwa', BA: 'Balochistan', IS: 'Islamabad', GB: 'Gilgit-Baltistan', JK: 'Azad Kashmir' },
  GB: { ENG: 'England', SCT: 'Scotland', WLS: 'Wales', NIR: 'Northern Ireland' },
  AE: { DU: 'Dubai', AZ: 'Abu Dhabi', SH: 'Sharjah', AJ: 'Ajman', RK: 'Ras Al Khaimah', FU: 'Fujairah', UQ: 'Umm Al Quwain' },
  SA: { '01': 'Riyadh', '02': 'Makkah', '03': 'Madinah', '04': 'Eastern Province' },
  CA: { ON: 'Ontario', QC: 'Quebec', BC: 'British Columbia', AB: 'Alberta', MB: 'Manitoba', SK: 'Saskatchewan', NS: 'Nova Scotia' },
  US: {
    AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California', CO: 'Colorado', CT: 'Connecticut',
    DE: 'Delaware', DC: 'Washington DC', FL: 'Florida', GA: 'Georgia', HI: 'Hawaii', ID: 'Idaho', IL: 'Illinois',
    IN: 'Indiana', IA: 'Iowa', KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana', ME: 'Maine', MD: 'Maryland',
    MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota', MS: 'Mississippi', MO: 'Missouri', MT: 'Montana',
    NE: 'Nebraska', NV: 'Nevada', NH: 'New Hampshire', NJ: 'New Jersey', NM: 'New Mexico', NY: 'New York',
    NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio', OK: 'Oklahoma', OR: 'Oregon', PA: 'Pennsylvania',
    RI: 'Rhode Island', SC: 'South Carolina', SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas', UT: 'Utah',
    VT: 'Vermont', VA: 'Virginia', WA: 'Washington', WV: 'West Virginia', WI: 'Wisconsin', WY: 'Wyoming',
  },
};

export function regionName(country: string, region: string): string {
  if (!region) return '';
  return REGION_NAMES[country.toUpperCase()]?.[region.toUpperCase()] || region;
}

/** The current local time somewhere, e.g. "9:14 PM", or '' for an unknown zone. */
export function localTime(timezone: string | null | undefined, now: Date = new Date()): string {
  if (!timezone) return '';
  try {
    return new Intl.DateTimeFormat('en-US', { timeZone: timezone, hour: 'numeric', minute: '2-digit' }).format(now);
  } catch {
    return '';
  }
}

/** Unicode flag emoji for a 2-letter country code. */
export function flagEmoji(code: string): string {
  if (!/^[A-Za-z]{2}$/.test(code)) return '';
  return String.fromCodePoint(...[...code.toUpperCase()].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65));
}
