'use client';

import { useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  ExternalLink,
  MessageSquareOff,
  Send,
  ShieldAlert,
  X,
} from 'lucide-react';
import { CONTACTED_STATUSES, STATUS_LABELS, todayPKT, waLink, type Lead, type LeadStatus } from '@/lib/lead-types';
import { WhatsappIcon } from '@/components/ui/BrandIcons';
import { leadsApi } from '@/components/admin/client-api';
import { Toast, useNotice } from '@/components/admin/ui';
import type { StorageMode } from '@/lib/leads';

/** New first-contact conversations per day that keep a personal number safe. */
const DAILY_LIMIT = 20;

type Tab = 'queue' | 'sent' | 'skipped';

export default function OutreachQueue({
  initialLeads,
  mode,
  sheetUrl,
}: {
  initialLeads: Lead[];
  mode: StorageMode;
  sheetUrl: string;
}) {
  const [leads, setLeads] = useState(initialLeads);
  const [tab, setTab] = useState<Tab>('queue');
  const [busyId, setBusyId] = useState<string | null>(null);
  const { toast, setToast, error, setError } = useNotice();

  const queued = useMemo(
    () =>
      leads
        .filter((lead) => lead.status === 'queued' && !lead.do_not_contact)
        .sort((a, b) => (b.lead_score || 0) - (a.lead_score || 0) || a.name.localeCompare(b.name)),
    [leads],
  );
  const sent = useMemo(
    () =>
      leads
        .filter((lead) => CONTACTED_STATUSES.includes(lead.status))
        .sort((a, b) => (b.last_contacted || '').localeCompare(a.last_contacted || '')),
    [leads],
  );
  const skipped = useMemo(() => leads.filter((lead) => lead.status === 'skipped'), [leads]);

  const list = tab === 'queue' ? queued : tab === 'sent' ? sent : skipped;

  async function patch(lead: Lead, status: LeadStatus, successMessage: string, note?: string) {
    setBusyId(lead.id);
    setError('');
    try {
      const updated = await leadsApi.patch(lead.id, note ? { status, append_note: note } : { status });
      setLeads((current) => current.map((row) => (row.id === lead.id ? updated : row)));
      setToast(successMessage);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update lead');
    } finally {
      setBusyId(null);
    }
  }

  async function copy(lead: Lead) {
    try {
      await navigator.clipboard.writeText(lead.message);
      setToast('Message copied — paste in WhatsApp');
    } catch {
      setError('Copy failed. Select the message text manually.');
    }
  }

  const counts = {
    queue: queued.length,
    sent: sent.length,
    skipped: skipped.length,
  };
  const total = leads.length;
  const done = sent.length + skipped.length;
  const progress = total ? Math.round((done / total) * 100) : 0;
  const today = todayPKT();
  const sentToday = leads.filter(
    (lead) =>
      lead.first_contacted === today ||
      (!lead.first_contacted && lead.last_contacted === today && CONTACTED_STATUSES.includes(lead.status)),
  ).length;
  const overLimit = sentToday >= DAILY_LIMIT;

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Outreach</p>
          <h1 className="mt-2 text-3xl font-bold">Send queue</h1>
          <p className="mt-1 text-sm text-fg-muted">
            {total} leads in this batch · {queued.length} waiting · {done} handled
          </p>
        </div>
        <div className="text-right">
          <p className="text-3xl font-bold">{progress}%</p>
          <p className="text-xs text-fg-subtle">batch complete</p>
          <p className={`mt-1 text-xs font-semibold ${overLimit ? 'text-red-500' : 'text-fg-muted'}`}>
            {sentToday} / {DAILY_LIMIT} first messages today
          </p>
          {sheetUrl && (
            <a
              href={sheetUrl}
              target="_blank"
              rel="noreferrer"
              className="mt-1 inline-flex items-center gap-1 text-xs text-fg-subtle transition hover:text-brand"
            >
              <ExternalLink className="size-3" /> Warehouse sheet
            </a>
          )}
        </div>
      </div>

      <div className="mt-4 h-2 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-cta transition-all" style={{ width: `${progress}%` }} />
      </div>

      {mode !== 'readonly' && (
        <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-fg-subtle">
          <span className="size-1.5 rounded-full bg-emerald-500" />
          {mode === 'supabase' ? 'Synced to Supabase — progress saves across devices.' : 'Saved locally in .data/leads.json.'}
        </p>
      )}

      <div className="mt-5 flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs leading-relaxed text-amber-700 dark:text-amber-400">
        <ShieldAlert className="mt-0.5 size-4 shrink-0" />
        <span>
          Send <strong>one at a time</strong>, from your own WhatsApp. Open chat → copy message → paste → send →
          mark sent. Keep it under ~15–20 new conversations a day to protect your number, and honour every STOP
          request immediately.
        </span>
      </div>

      {overLimit && (
        <div className="mt-3 flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-xs leading-relaxed text-red-600 dark:text-red-400">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <span>
            You have sent {sentToday} first messages today. Stop here and continue tomorrow — bursts of new chats are the
            main reason WhatsApp restricts numbers.
          </span>
        </div>
      )}

      {mode === 'readonly' && (
        <div className="mt-3 flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs leading-relaxed text-amber-700 dark:text-amber-400">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <span>No database connected. Connect Supabase to load and track the outreach queue.</span>
        </div>
      )}

      {error && (
        <div className="mt-3 flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-500">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <span>{error}</span>
          <button onClick={() => setError('')} className="ml-auto" aria-label="Dismiss">
            <X className="size-4" />
          </button>
        </div>
      )}

      <div className="mt-6 flex flex-wrap gap-2">
        {(
          [
            ['queue', `Queue (${counts.queue})`],
            ['sent', `Sent (${counts.sent})`],
            ['skipped', `Not on WhatsApp (${counts.skipped})`],
          ] as [Tab, string][]
        ).map(([value, label]) => (
          <button
            key={value}
            onClick={() => setTab(value)}
            className={`h-9 rounded-full border px-4 text-sm font-semibold transition ${
              tab === value
                ? 'border-brand bg-brand-soft text-brand'
                : 'border-line text-fg-muted hover:border-brand/50 hover:text-brand'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="mt-4 space-y-3">
        {list.map((lead, index) => (
          <article key={lead.id} className="card p-4 sm:p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="grid size-7 shrink-0 place-items-center rounded-full bg-muted text-xs font-bold text-fg-muted">
                    {tab === 'queue' ? index + 1 : '✓'}
                  </span>
                  <h2 className="truncate font-bold">{lead.name}</h2>
                  <span className="rounded-full border border-line px-2 py-0.5 text-[10px] font-semibold uppercase text-fg-subtle">
                    {lead.lead_tier} · {lead.lead_score}
                  </span>
                </div>
                <p className="mt-1 text-xs text-fg-subtle">
                  {lead.business_type} · {lead.area} · <span className="font-mono">{lead.phone}</span>
                </p>
              </div>
              <span
                className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${
                  lead.status === 'skipped'
                    ? 'border-line bg-muted text-fg-muted'
                    : lead.status === 'queued'
                      ? 'border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400'
                      : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                }`}
              >
                {STATUS_LABELS[lead.status]}
              </span>
            </div>

            <p className="mt-3 whitespace-pre-wrap rounded-xl border border-line bg-muted/40 px-3 py-2.5 text-[13px] leading-relaxed text-fg-muted">
              {lead.message || 'No message drafted yet — add one from the Leads page.'}
            </p>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              {!lead.do_not_contact && (
              <a
                href={waLink(lead)}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex h-9 items-center gap-1.5 rounded-full bg-[#25d366] px-4 text-sm font-semibold text-white transition hover:brightness-105"
              >
                <WhatsappIcon className="size-4" /> Open chat
              </a>
              )}
              <button
                type="button"
                onClick={() => copy(lead)}
                className="inline-flex h-9 items-center gap-1.5 rounded-full border border-line px-3 text-sm font-semibold text-fg-muted transition hover:border-brand hover:text-brand"
              >
                <Copy className="size-3.5" /> Copy message
              </button>
              {tab === 'queue' && (
                <>
                  <button
                    type="button"
                    onClick={() => patch(lead, 'contacted', 'Marked as sent')}
                    disabled={busyId === lead.id}
                    className="inline-flex h-9 items-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-3 text-sm font-semibold text-emerald-700 transition hover:bg-emerald-500/20 disabled:opacity-50 dark:text-emerald-400"
                  >
                    <CheckCircle2 className="size-3.5" /> Mark sent
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      patch(lead, 'skipped', 'Marked as not on WhatsApp', 'Not on WhatsApp (checked).')
                    }
                    disabled={busyId === lead.id}
                    className="inline-flex h-9 items-center gap-1.5 rounded-full border border-line px-3 text-sm font-semibold text-fg-muted transition hover:border-red-400 hover:text-red-500 disabled:opacity-50"
                  >
                    <MessageSquareOff className="size-3.5" /> Not on WhatsApp
                  </button>
                </>
              )}
              {tab !== 'queue' && !lead.do_not_contact && (
                <button
                  type="button"
                  onClick={() => patch(lead, 'queued', 'Moved back to queue')}
                  disabled={busyId === lead.id}
                  className="inline-flex h-9 items-center gap-1.5 rounded-full border border-line px-3 text-sm font-semibold text-fg-muted transition hover:border-brand hover:text-brand disabled:opacity-50"
                >
                  <Send className="size-3.5" /> Requeue
                </button>
              )}
            </div>
          </article>
        ))}

        {list.length === 0 && (
          <div className="card grid place-items-center gap-2 p-10 text-center">
            <CheckCircle2 className="size-8 text-emerald-500" />
            <p className="font-semibold">
              {tab === 'queue' ? 'Queue is clear' : tab === 'sent' ? 'Nothing sent yet' : 'Nothing marked unavailable'}
            </p>
            <p className="text-sm text-fg-muted">
              {tab === 'queue'
                ? 'All leads in this batch are handled. Import the next batch when you are ready.'
                : 'Statuses you set here are saved to the CRM.'}
            </p>
          </div>
        )}
      </div>

      <Toast message={toast} />
    </div>
  );
}

