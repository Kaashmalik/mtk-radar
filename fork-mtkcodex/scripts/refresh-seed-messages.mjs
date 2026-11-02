/**
 * One-off: clean the seed batch names + regenerate professional, scenario-aware
 * WhatsApp openers.
 *
 * Usage: node scripts/refresh-seed-messages.mjs
 */
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const file = path.join(process.cwd(), '.data', 'leads.seed.json');
const leads = JSON.parse(readFileSync(file, 'utf8'));

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
  if (scenario === 'no_website') {
    return "I noticed you don't have a website yet, so I thought it was worth reaching out.";
  }
  if (scenario === 'has_website') {
    return 'I had a look at your website and noticed a few quick ways it could bring in more enquiries.';
  }
  if (scenario === 'maintenance') {
    return 'I noticed a few ways your website could be working harder for the business.';
  }
  return 'I wanted to introduce what we do for businesses like yours.';
}

/**
 * Some scraped names mix Latin and Urdu script (e.g. "DHA Main Office Complex?? ???
 * ?? ???"). Keep the Latin part so the WhatsApp opener reads cleanly; the full
 * record and Maps link stay untouched.
 */
function displayName(name) {
  const withoutTrailingScript = name.replace(/\s*\?{2,}.*$/, '').trim();
  const latin = withoutTrailingScript.replace(/[^\x20-\x7E]/g, ' ').replace(/\s+/g, ' ').trim();
  return latin.length >= 3 ? latin : name;
}

for (const lead of leads) {
  lead.name = displayName(lead.name);
  lead.message = [
    `Assalam-o-Alaikum ${lead.name}, this is Kashif from MTK Codex (mtkcodex.tech), a software company in Lahore.`,
    `I came across your business in ${lead.area}. ${reason(lead.scenario)}`,
    `We build ${offer(lead.business_type, lead.name)} — with a free consultation and a fixed quote before any work begins.`,
    `Would a short call this week be useful? If not, reply STOP and I won't message again.`,
  ].join(' ');
  if (lead.status === 'contacted') {
    lead.notes = 'Contacted earlier on 2026-11-02 with the previous batch template. Record kept for follow-up.';
  }
}

writeFileSync(file, `${JSON.stringify(leads, null, 2)}\n`, 'utf8');
console.log(`refreshed ${leads.length} seed leads`);
