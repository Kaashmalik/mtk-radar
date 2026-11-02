/**
 * Import a WhatsApp "sent" log (the CSV the outreach pack produces) into the CRM.
 *
 * The scraper pipeline already mirrors sends into the Google Sheet; this script
 * brings the same truth into the CRM so the dashboard and the send queue agree.
 *
 * Usage:
 *   node scripts/import-sent-log.mjs "C:\path\to\sent_2026-11-02.csv"            # dry run
 *   node scripts/import-sent-log.mjs "C:\path\to\sent_2026-11-02.csv" --apply    # write
 *
 * Options:
 *   --apply                 Write changes (default is a dry run)
 *   --date=YYYY-MM-DD       Send date (default: parsed from the file name, else today)
 *   --followup-days=3       Days until the next follow-up for new rows (default 3)
 *
 * Behaviour:
 *   - Matches by lead_id first, then by phone number.
 *   - Existing leads become `contacted`, keep their notes and gain a dated marker.
 *   - New leads are created as `contacted` with a scenario-aware opener.
 *   - Idempotent: re-running the same file does not duplicate notes.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const file = args.find((a) => !a.startsWith('--'));
const apply = args.includes('--apply');
const dateArg = args.find((a) => a.startsWith('--date='))?.split('=')[1];
const followupDays = Number(args.find((a) => a.startsWith('--followup-days='))?.split('=')[1] || 3);

if (!file) {
  console.error('Usage: node scripts/import-sent-log.mjs <sent.csv> [--apply] [--date=YYYY-MM-DD]');
  process.exit(1);
}

const env = Object.fromEntries(
  readFileSync(path.join(process.cwd(), '.env.local'), 'utf8')
    .split(/\r?\n/)
    .filter((line) => /^[A-Z0-9_]+=/.test(line))
    .map((line) => [line.slice(0, line.indexOf('=')), line.slice(line.indexOf('=') + 1).trim()]),
);
const SUPABASE_URL = env.SUPABASE_URL;
const SUPABASE_KEY = env.SUPABASE_SERVICE_ROLE_KEY;
if (!SUPABASE_URL || !SUPABASE_KEY) {
  console.error('SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env.local.');
  process.exit(1);
}

// Dates are calendar days in the owner's timezone (Asia/Karachi), like the CRM.
const pkt = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Karachi', year: 'numeric', month: '2-digit', day: '2-digit' });
const sendDate =
  dateArg ||
  (path.basename(file).match(/(\d{4}-\d{2}-\d{2})/)?.[1] ?? pkt.format(new Date()));
// Noon UTC is the same calendar day in Karachi, so adding whole days is safe.
const followupDate = new Date(`${sendDate}T12:00:00Z`);
followupDate.setUTCDate(followupDate.getUTCDate() + followupDays);
const followup = followupDate.toISOString().slice(0, 10);

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = '';
  let quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') quoted = false;
      else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === ',') { row.push(cell); cell = ''; }
    else if (c === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; }
    else if (c !== '\r') cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

const raw = parseCsv(readFileSync(file, 'utf8').replace(/^\uFEFF/, ''));
const header = raw[0];
const sent = raw
  .slice(1)
  .filter((row) => row.some(Boolean))
  .map((row) => Object.fromEntries(header.map((key, i) => [key, (row[i] ?? '').trim()])));

function offer(type = '', name = '') {
  if (/driving/i.test(name)) return 'driving-school websites with online lesson booking';
  if (type.startsWith('Corporate')) return 'professional firm websites with enquiry funnels and appointment booking';
  if (type.startsWith('Construction')) return 'property and project websites with enquiry tracking';
  if (type.startsWith('Education')) return 'school websites with online admissions and fee portals';
  if (type.startsWith('Printing')) return 'websites with online catalogues and order enquiries';
  if (type.startsWith('Healthcare')) return 'clinic websites with appointment booking and patient records';
  if (type.startsWith('Electronics')) return 'product catalogues and service booking';
  if (type.startsWith('Restaurant')) return 'restaurant websites with menus and online ordering';
  if (type.startsWith('Gym')) return 'gym websites with membership plans and online sign-ups';
  if (type.startsWith('Beauty') || type.startsWith('Bridal')) return 'booking websites with service menus';
  if (type.startsWith('Retail')) return 'online catalogues and e-commerce stores';
  if (type.startsWith('Manufacturer')) return 'B2B catalogues with inventory and dispatch';
  if (type.startsWith('Wholesale')) return 'B2B ordering portals with stock and invoicing';
  return 'professional websites and business systems';
}

function reason(scenario = '') {
  if (scenario === 'no_website') return "I noticed you don't have a website yet, so I thought it was worth reaching out.";
  if (scenario === 'has_website') return 'I had a look at your website and noticed a few quick ways it could bring in more enquiries.';
  if (scenario === 'maintenance') return 'I noticed a few ways your website could be working harder for the business.';
  return 'I wanted to introduce what we do for businesses like yours.';
}

function displayName(name) {
  const withoutTrailingScript = name.replace(/\s*\?{2,}.*$/, '').trim();
  const latin = withoutTrailingScript.replace(/[^\x20-\x7E]/g, ' ').replace(/\s+/g, ' ').trim();
  return latin.length >= 3 ? latin : name;
}

function message(lead) {
  return [
    `Assalam-o-Alaikum ${lead.name}, this is Kashif from MTK Codex (mtkcodex.tech), a software company in Lahore.`,
    `I came across your business in ${lead.area}. ${reason(lead.scenario)}`,
    `We build ${offer(lead.business_type, lead.name)} — with a free consultation and a fixed quote before any work begins.`,
    `Would a short call this week be useful? If not, reply STOP and I won't message again.`,
  ].join(' ');
}

const digits = (value = '') => value.replace(/\D/g, '');
const noteMarker = `WhatsApp sent ${sendDate} (1 touch)`;

async function supabase(pathAndQuery, init = {}) {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${pathAndQuery}`, {
    ...init,
    headers: {
      apikey: SUPABASE_KEY,
      Authorization: `Bearer ${SUPABASE_KEY}`,
      'Content-Type': 'application/json',
      ...(init.headers || {}),
    },
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`Supabase ${res.status}: ${text.slice(0, 300)}`);
  return text ? JSON.parse(text) : null;
}

const existing = await supabase('leads?select=*');
const byId = new Map(existing.map((lead) => [lead.id, lead]));
const byPhone = new Map(existing.map((lead) => [digits(lead.phone), lead]).filter(([key]) => key));

const updates = [];
const inserts = [];
const unchanged = [];

for (const row of sent) {
  const name = displayName(row.name || row.contact_name || '');
  if (!name) continue;
  const match = byId.get(row.lead_id) || byPhone.get(digits(row.phone_e164));
  const notes = [match?.notes?.trim(), noteMarker].filter(Boolean).join('; ');

  if (match) {
    const already = (match.notes || '').includes(noteMarker) && match.status === 'contacted';
    if (already) { unchanged.push(name); continue; }
    updates.push({
      id: match.id,
      name,
      patch: {
        status: 'contacted',
        last_contacted: match.last_contacted && match.last_contacted > sendDate ? match.last_contacted : sendDate,
        next_followup: match.next_followup || followup,
        notes,
      },
    });
    continue;
  }

  inserts.push({
    id: row.lead_id,
    name,
    business_type: row.business_type || '',
    area: row.area || '',
    phone: row.phone_e164 || '',
    email: row.email || '',
    website: '',
    lead_score: Number(row.lead_score) || 0,
    lead_tier: row.lead_tier || 'C',
    scenario: row.scenario || '',
    rating: row.google_rating ? Number(row.google_rating) : null,
    reviews: row.google_review_count ? Number(row.google_review_count) : null,
    google_maps_url: row.google_maps_url || '',
    recommended_pitch: row.recommended_pitch || '',
    message: message({ name, area: row.area || '', scenario: row.scenario, business_type: row.business_type }),
    status: 'contacted',
    channel: 'whatsapp',
    notes: noteMarker,
    last_contacted: sendDate,
    next_followup: followup,
    do_not_contact: false,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  });
}

console.log(`Sent log      : ${path.basename(file)}`);
console.log(`Send date     : ${sendDate} (follow-up ${followup})`);
console.log(`Rows read     : ${sent.length}`);
console.log(`Already synced: ${unchanged.length}`);
console.log(`Will update   : ${updates.length}`);
console.log(`Will insert   : ${inserts.length}`);
for (const item of updates) console.log(`  update  ${item.name}`);
for (const item of inserts) console.log(`  insert  ${item.name}`);

if (!apply) {
  console.log('\nDRY RUN — pass --apply to write to Supabase.');
  process.exit(0);
}

for (const { id, patch } of updates) {
  await supabase(`leads?id=eq.${encodeURIComponent(id)}&select=id`, {
    method: 'PATCH',
    headers: { Prefer: 'return=representation' },
    body: JSON.stringify(patch),
  });
}
if (inserts.length) {
  await supabase('leads?on_conflict=id&select=id', {
    method: 'POST',
    headers: { Prefer: 'resolution=merge-duplicates,return=representation' },
    body: JSON.stringify(inserts),
  });
}

const after = await supabase('leads?select=status');
const counts = after.reduce((acc, lead) => ({ ...acc, [lead.status]: (acc[lead.status] || 0) + 1 }), {});
console.log(`\nAPPLIED — ${updates.length} updated, ${inserts.length} inserted.`);
console.log(`CRM now       : ${after.length} leads · ${JSON.stringify(counts)}`);
