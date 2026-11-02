/**
 * Renders .data/leads.seed.json into a markdown batch record under .data/outreach/.
 * Both are gitignored: batch records contain real phone numbers and must stay private.
 *
 * Usage: node scripts/outreach-doc.mjs [YYYY-MM-DD] [slug]
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const seedPath = path.join(process.cwd(), '.data', 'leads.seed.json');
const leads = JSON.parse(readFileSync(seedPath, 'utf8'));

const date = process.argv[2] || new Date().toISOString().slice(0, 10);
const slug = process.argv[3] || 'batch';
const outPath = path.join(process.cwd(), '.data', 'outreach', `${date}-${slug}.md`);

const queued = leads.filter((lead) => lead.status === 'queued').length;
const contacted = leads.filter((lead) => lead.status === 'contacted').length;
const areas = [...new Set(leads.map((lead) => lead.area).filter(Boolean))];

const lines = [];
lines.push(`# Outreach batch — ${date}`);
lines.push('');
lines.push('Source: `today_batch_check.csv` (Lahore lead scraper output).');
lines.push('');
lines.push(
  `Batch size: **${leads.length} leads** · Queued: **${queued}** · Already contacted earlier: **${contacted}**`,
);
lines.push('');
lines.push(`Areas: ${areas.join(', ')}.`);
lines.push('');
lines.push(
  '> Leads already messaged on the same day are recorded as `contacted` and excluded from the send queue to avoid duplicate messages.',
);
lines.push('');
lines.push('## Batch table');
lines.push('');
lines.push('| # | Business | Type | Area | Phone | Status |');
lines.push('|---|---|---|---|---|---|');
leads.forEach((lead, index) => {
  const status = lead.status === 'contacted' ? 'Contacted (earlier)' : lead.status === 'queued' ? 'Queued' : lead.status;
  lines.push(`| ${index + 1} | ${lead.name} | ${lead.business_type} | ${lead.area} | ${lead.phone} | ${status} |`);
});
lines.push('');
lines.push('## Messages');
lines.push('');
lines.push('Each message is also stored in the CRM (`leads.message`) and pre-filled in the WhatsApp link.');
lines.push('');
leads.forEach((lead, index) => {
  const digits = lead.phone.replace(/\D/g, '');
  lines.push(`### ${index + 1}. ${lead.name}`);
  lines.push('');
  lines.push(`- Type: ${lead.business_type}`);
  lines.push(`- Area: ${lead.area}`);
  lines.push(
    `- Phone: \`${lead.phone}\` · Score: ${lead.lead_score} (${lead.lead_tier}) · Scenario: ${lead.scenario}`,
  );
  if (lead.google_maps_url) lines.push(`- Maps: ${lead.google_maps_url}`);
  lines.push('');
  lines.push('```text');
  lines.push(lead.message);
  lines.push('```');
  lines.push('');
  lines.push(`[Open WhatsApp](https://wa.me/${digits}) · Status: ${lead.status}`);
  lines.push('');
});
lines.push('## Result log');
lines.push('');
lines.push('Update after each sending session (or rely on the CRM export).');
lines.push('');
lines.push('| Date | Sent | Not on WhatsApp | Replies | Notes |');
lines.push('|---|---|---|---|---|');
lines.push(`| ${date} | 0 / ${queued} | 0 | 0 | Batch prepared; queue ready in \`/admin/outreach\`. |`);
lines.push('');

mkdirSync(path.dirname(outPath), { recursive: true });
writeFileSync(outPath, lines.join('\n'), 'utf8');
console.log(`wrote ${path.relative(process.cwd(), outPath)} (${leads.length} leads)`);
