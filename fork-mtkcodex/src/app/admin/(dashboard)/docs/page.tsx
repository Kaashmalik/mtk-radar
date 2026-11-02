import Link from 'next/link';
import { ArrowLeft, BookOpen, Database, MessageSquare, ShieldCheck } from 'lucide-react';

export const metadata = {
  title: 'Outreach playbook',
  robots: { index: false, follow: false },
};

const statuses: [string, string][] = [
  ['New', 'Imported lead, not yet reviewed.'],
  ['Queued', 'Approved and waiting to be messaged.'],
  ['Contacted', 'First message sent. Set a follow-up date.'],
  ['Replied', 'They responded — keep the thread moving.'],
  ['Interested', 'Qualified: wants a call, quote or demo.'],
  ['Won', 'Paid client. Move to delivery.'],
  ['Lost', 'Declined or not a fit. Keep for records, stop outreach.'],
  ['Not on WhatsApp', 'Number is not on WhatsApp (or unreachable).'],
];

export default function AdminDocsPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <Link href="/admin" className="inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-brand">
        <ArrowLeft className="size-4" /> Back to leads
      </Link>

      <p className="eyebrow mt-6">Playbook</p>
      <h1 className="mt-2 text-3xl font-bold">Admin &amp; CRM runbook</h1>
      <p className="mt-2 text-sm leading-relaxed text-fg-muted">
        Short version of <code className="rounded bg-muted px-1">docs/CRM.md</code> in the repository. Keep this page in sync
        with the repo when the process changes.
      </p>

      <Section icon={ShieldCheck} title="Access & security">
        <ul className="list-disc space-y-2 pl-5">
          <li>
            Sign in at <code className="rounded bg-muted px-1">/admin/login</code> with the owner email and the password
            in <code className="rounded bg-muted px-1">ADMIN_PASSWORD</code>. Sessions last 8 hours and are signed with{' '}
            <code className="rounded bg-muted px-1">ADMIN_SESSION_SECRET</code>.
          </li>
          <li>Change the password in Vercel → Settings → Environment Variables, then redeploy.</li>
          <li>Never commit credentials. <code>.env.local</code> is gitignored.</li>
          <li><code>/admin</code> is excluded from search engines and the sitemap.</li>
        </ul>
      </Section>

      <Section icon={Database} title="Where the data lives">
        <ul className="list-disc space-y-2 pl-5">
          <li>
            <strong>Production:</strong> Supabase Postgres, table <code>leads</code> (service-role key, RLS on). Set{' '}
            <code>SUPABASE_URL</code> and <code>SUPABASE_SERVICE_ROLE_KEY</code>.
          </li>
          <li>
            <strong>Local dev:</strong> falls back to JSON files in <code>.data/</code> (gitignored), seeded from a
            private <code>.data/leads.seed.json</code> if present.
          </li>
          <li>
            <strong>No database on Vercel:</strong> the CRM is empty and read-only until Supabase is connected.
          </li>
          <li>
            Import new batches with <em>Import</em> on the Leads page (CSV or a Google Sheet link). Never commit lead
            data to the repository.
          </li>
          <li>Use <em>Export CSV</em> for backups or to sync back into the scraping pipeline.</li>
          <li>
            The scraper keeps a Google Sheet warehouse (linked from this page). After sending, reconcile the
            sent log into the CRM with <code className="rounded bg-muted px-1">scripts/import-sent-log.mjs</code>.
          </li>
        </ul>
      </Section>

      <Section icon={MessageSquare} title="Inbox: live chat, WhatsApp and email">
        <ul className="list-disc space-y-2 pl-5">
          <li>
            Keep <Link href="/admin/inbox" className="font-semibold text-brand">Inbox</Link> open (or the installed app) —
            that is what shows website visitors you are online.
          </li>
          <li>Every chat shows the visitor&rsquo;s city, country and local time. Reply at a sensible hour for them.</li>
          <li>If a chat visitor has left but shared an email, your reply is emailed with a link back to the chat.</li>
          <li>US/UK clients: reply by email and offer the booking link for a video call.</li>
          <li>
            Turn on phone alerts in <Link href="/admin/settings" className="font-semibold text-brand">Settings</Link>.
          </li>
        </ul>
      </Section>

      <Section icon={MessageSquare} title="Daily outreach routine">
        <ol className="list-decimal space-y-2 pl-5">
          <li>Open <Link href="/admin/outreach" className="font-semibold text-brand">Outreach</Link>, work top-down (highest score first).</li>
          <li>Click <strong>Open chat</strong>, then <strong>Copy message</strong>, paste and send from your own WhatsApp.</li>
          <li>Click <strong>Mark sent</strong>. The CRM stamps today&rsquo;s date. Set a follow-up 2–3 days out in the lead drawer.</li>
          <li>If WhatsApp says the number is invalid, use <strong>Not on WhatsApp</strong>. This records the reason and stops retries.</li>
          <li>Anyone who asks to stop: tick <strong>Do not contact</strong> in the lead drawer before anything else.</li>
          <li>Keep new conversations under ~15–20 per day per number, spaced through the day.</li>
        </ol>
      </Section>

      <Section icon={BookOpen} title="Status meanings">
        <div className="overflow-hidden rounded-xl border border-line">
          <table className="w-full text-left text-sm">
            <tbody>
              {statuses.map(([status, meaning]) => (
                <tr key={status} className="border-b border-line last:border-0">
                  <th className="w-40 px-3 py-2 font-semibold">{status}</th>
                  <td className="px-3 py-2 text-fg-muted">{meaning}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section icon={BookOpen} title="Message rules">
        <ul className="list-disc space-y-2 pl-5">
          <li>Lead with their business name and area so it is obviously personal, not bulk.</li>
          <li>One clear ask: a 3-minute call or a yes/no reply. No attachments or links in the first message.</li>
          <li>Never claim they have no website unless the CRM scenario is <code>no_website</code>.</li>
          <li>Always keep the <em>Reply STOP to opt out</em> line.</li>
          <li>Follow up once after 2–3 days, then stop. Two unanswered messages is the limit.</li>
        </ul>
      </Section>

      <div className="mt-8 rounded-xl border border-line bg-muted/40 p-4 text-xs leading-relaxed text-fg-muted">
        Batch records are private and live in <code>.data/outreach/</code> (gitignored). Database migrations:{' '}
        <code>supabase/migrations/0001</code> → <code>0004</code>, run in order. Full guide: <code>docs/CRM.md</code>.
      </div>
    </div>
  );
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof ShieldCheck;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-8">
      <h2 className="flex items-center gap-2 text-lg font-bold">
        <span className="grid size-8 place-items-center rounded-lg bg-brand-soft text-brand">
          <Icon className="size-4" />
        </span>
        {title}
      </h2>
      <div className="mt-3 text-sm leading-relaxed text-fg-muted">{children}</div>
    </section>
  );
}
