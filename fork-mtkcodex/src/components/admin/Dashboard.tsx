'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Ban,
  Briefcase,
  CalendarClock,
  Download,
  ExternalLink,
  Inbox,
  MessageCircle,
  RefreshCw,
  Search,
  Send,
  Star,
  Trash2,
  Upload,
  UserPlus,
  Users,
  X,
} from 'lucide-react';
import {
  DEAL_STAGE_LABELS,
  LEAD_STATUSES,
  STATUS_LABELS,
  addDaysPKT,
  canMessage,
  dealTone,
  flagEmoji,
  formatMoney,
  leadStats,
  leadsToCsv,
  phoneDigits,
  statusTone,
  todayPKT,
  waLink,
  type Lead,
  type LeadStatus,
} from '@/lib/lead-types';
import { WhatsappIcon } from '@/components/ui/BrandIcons';
import LiveTraffic from '@/components/admin/LiveTraffic';
import LeadDrawer from '@/components/admin/LeadDrawer';
import ImportDialog from '@/components/admin/ImportDialog';
import AddLeadDialog from '@/components/admin/AddLeadDialog';
import TodayPanel, { type ActivityPoint, type FeedItem } from '@/components/admin/TodayPanel';
import { downloadText, leadsApi, type LeadPatchBody } from '@/components/admin/client-api';
import { ErrorBanner, Notice, StatCard, Toast, buttonClass, primaryButtonClass, useNotice } from '@/components/admin/ui';
import type { AnalyticsSummary } from '@/lib/analytics-types';
import type { StorageMode } from '@/lib/leads';

type Quick = 'starred' | 'due' | 'unread' | 'deals';
type Sort = 'newest' | 'score' | 'last_contacted' | 'followup' | 'reply';

const PAGE = 50;

export default function Dashboard({
  initialLeads,
  mode,
  email,
  analytics,
  points,
  feed,
  whatsappEnabled,
  sheetUrl,
}: {
  initialLeads: Lead[];
  mode: StorageMode;
  email: string;
  analytics: AnalyticsSummary | null;
  points: ActivityPoint[];
  feed: FeedItem[];
  whatsappEnabled: boolean;
  sheetUrl: string;
}) {
  const [leads, setLeads] = useState(initialLeads);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<'all' | LeadStatus>('all');
  const [tier, setTier] = useState('all');
  const [source, setSource] = useState('all');
  const [quick, setQuick] = useState<Set<Quick>>(new Set());
  const [hideOptOut, setHideOptOut] = useState(false);
  const [sort, setSort] = useState<Sort>('newest');
  const [visible, setVisible] = useState(PAGE);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [busyId, setBusyId] = useState<string | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [dialog, setDialog] = useState<'import' | 'add' | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const { toast, setToast, error, setError, fail } = useNotice();

  const readOnly = mode === 'readonly';
  const stats = useMemo(() => leadStats(leads), [leads]);
  const selected = leads.find((lead) => lead.id === selectedId) || null;
  const today = todayPKT();

  // Deep link: /admin?lead=<id> opens the drawer (used by the inbox).
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get('lead');
    if (id) setSelectedId(id);
  }, []);

  const tiers = useMemo(() => [...new Set(leads.map((l) => l.lead_tier).filter(Boolean))].sort(), [leads]);
  const sources = useMemo(() => [...new Set(leads.map((l) => l.source || 'scraper'))].sort(), [leads]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const rows = leads.filter((lead) => {
      if (status !== 'all' && lead.status !== status) return false;
      if (tier !== 'all' && lead.lead_tier !== tier) return false;
      if (source !== 'all' && (lead.source || 'scraper') !== source) return false;
      if (hideOptOut && lead.do_not_contact) return false;
      if (quick.has('starred') && !lead.starred) return false;
      if (quick.has('unread') && !(lead.unread_count || 0)) return false;
      if (quick.has('deals') && (!lead.deal_stage || lead.deal_stage === 'none')) return false;
      if (quick.has('due') && !(lead.next_followup && lead.next_followup <= today && !['won', 'lost'].includes(lead.status))) {
        return false;
      }
      if (!needle) return true;
      return [lead.name, lead.business_type, lead.area, lead.phone, lead.notes, lead.email, ...(lead.tags || [])]
        .join(' ')
        .toLowerCase()
        .includes(needle);
    });
    const by: Record<Sort, (a: Lead, b: Lead) => number> = {
      newest: (a, b) => (b.created_at || '').localeCompare(a.created_at || '') || (b.lead_score || 0) - (a.lead_score || 0),
      score: (a, b) => (b.lead_score || 0) - (a.lead_score || 0),
      last_contacted: (a, b) => (b.last_contacted || '').localeCompare(a.last_contacted || ''),
      followup: (a, b) => (a.next_followup || '9999').localeCompare(b.next_followup || '9999'),
      reply: (a, b) => (b.last_inbound_at || '').localeCompare(a.last_inbound_at || ''),
    };
    return rows.sort(by[sort]);
  }, [leads, query, status, tier, source, quick, hideOptOut, sort, today]);

  const shown = filtered.slice(0, visible);
  const allShownChecked = shown.length > 0 && shown.every((lead) => checked.has(lead.id));

  const replaceLead = useCallback((lead: Lead) => setLeads((rows) => rows.map((row) => (row.id === lead.id ? lead : row))), []);

  async function reload() {
    setRefreshing(true);
    try {
      const data = await leadsApi.list();
      setLeads(data.leads);
      setToast('Refreshed');
    } catch (err) {
      fail(err);
    } finally {
      setRefreshing(false);
    }
  }

  async function quickPatch(lead: Lead, patch: LeadPatchBody, message: string) {
    setBusyId(lead.id);
    setError('');
    try {
      replaceLead(await leadsApi.patch(lead.id, patch));
      setToast(message);
    } catch (err) {
      fail(err);
    } finally {
      setBusyId(null);
    }
  }

  async function bulk(patch: LeadPatchBody, label: string) {
    const ids = [...checked];
    if (!ids.length) return;
    setBulkBusy(true);
    setError('');
    try {
      const result = await leadsApi.bulkPatch(ids, patch);
      const byId = new Map(result.updated.map((lead) => [lead.id, lead]));
      setLeads((rows) => rows.map((row) => byId.get(row.id) || row));
      setToast(`${label}: ${result.updated.length} updated`);
      if (result.errors.length) setError(`${result.errors.length} not updated — ${result.errors[0].error}`);
      setChecked(new Set());
    } catch (err) {
      fail(err);
    } finally {
      setBulkBusy(false);
    }
  }

  async function bulkDelete() {
    const ids = [...checked];
    if (!ids.length || !window.confirm(`Delete ${ids.length} lead(s) and their history? This cannot be undone.`)) return;
    setBulkBusy(true);
    try {
      const { deleted } = await leadsApi.remove(ids);
      const set = new Set(ids);
      setLeads((rows) => rows.filter((row) => !set.has(row.id)));
      setChecked(new Set());
      setToast(`Deleted ${deleted} lead(s)`);
    } catch (err) {
      fail(err);
    } finally {
      setBulkBusy(false);
    }
  }

  function exportRows(rows: Lead[], label: string) {
    downloadText(leadsToCsv(rows), `mtk-leads-${label}-${today}.csv`);
    setToast(`Exported ${rows.length} leads`);
  }

  function toggleQuick(value: Quick) {
    setQuick((current) => {
      const next = new Set(current);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
    setVisible(PAGE);
  }

  function toggleChecked(id: string) {
    setChecked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Lead CRM</p>
          <h1 className="mt-2 text-3xl font-bold">Pipeline</h1>
          <p className="mt-1 text-sm text-fg-muted">
            Signed in as {email}. {stats.total} leads · {stats.contacted} contacted · {stats.replyRate}% reply rate.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <a href="/admin/outreach" className={primaryButtonClass}>
            <Send className="size-4" /> Outreach ({stats.queued})
          </a>
          {whatsappEnabled && (
            <a href="/admin/inbox" className={buttonClass}>
              <Inbox className="size-4" /> Inbox
              {stats.unread > 0 && <span className="rounded-full bg-cta px-1.5 text-[11px] text-on-cta">{stats.unread}</span>}
            </a>
          )}
          <button type="button" onClick={() => setDialog('add')} disabled={readOnly} className={buttonClass}>
            <UserPlus className="size-4" /> Add
          </button>
          <button type="button" onClick={() => setDialog('import')} disabled={readOnly} className={buttonClass}>
            <Upload className="size-4" /> Import
          </button>
          <a href="/api/admin/leads/export" className={buttonClass} title="All leads as CSV (opens in Excel / Google Sheets)">
            <Download className="size-4" /> Export all
          </a>
          {sheetUrl && (
            <a href={sheetUrl} target="_blank" rel="noreferrer" className={buttonClass}>
              <ExternalLink className="size-4" /> Sheet
            </a>
          )}
          <button type="button" onClick={reload} className={buttonClass} aria-label="Refresh leads">
            <RefreshCw className={`size-4 ${refreshing ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <StorageNotice mode={mode} />

      <LiveTraffic initial={analytics} compact />

      <ErrorBanner message={error} onDismiss={() => setError('')} />

      <div className="mt-6 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard icon={Users} label="Total leads" value={stats.total} onClick={() => setStatus('all')} active={status === 'all'} />
        <StatCard icon={Send} label="Queued" value={stats.queued} onClick={() => setStatus('queued')} active={status === 'queued'} />
        <StatCard
          icon={MessageCircle}
          label="Contacted"
          value={stats.contacted}
          hint={`${stats.replyRate}% replied`}
          onClick={() => setStatus('contacted')}
          active={status === 'contacted'}
        />
        <StatCard
          icon={Star}
          label="Interested"
          value={stats.byStatus.interested}
          hint={`${stats.starred} starred`}
          onClick={() => setStatus('interested')}
          active={status === 'interested'}
        />
        <StatCard
          icon={CalendarClock}
          label="Follow-ups due"
          value={stats.dueToday}
          onClick={() => toggleQuick('due')}
          active={quick.has('due')}
        />
        <a href="/admin/deals" className="contents">
          <StatCard
            icon={Briefcase}
            label={`${stats.openDeals} open deals · ${stats.won} won`}
            value={formatMoney(stats.pipelineValue)}
            hint={stats.wonValue ? `${formatMoney(stats.wonValue)} won` : 'pipeline value'}
          />
        </a>
      </div>

      <TodayPanel leads={leads} points={points} feed={feed} onOpen={setSelectedId} />

      <div className="mt-8 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-fg-subtle" />
          <input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setVisible(PAGE);
            }}
            placeholder="Search business, area, phone, notes or tags…"
            aria-label="Search leads"
            className="h-10 w-full rounded-full border border-line bg-elevated pl-9 pr-4 text-sm outline-none transition focus:border-brand"
          />
        </div>
        <Select value={status} onChange={(v) => setStatus(v as 'all' | LeadStatus)} label="Status">
          <option value="all">All statuses</option>
          {LEAD_STATUSES.map((value) => (
            <option key={value} value={value}>
              {STATUS_LABELS[value]} ({stats.byStatus[value] || 0})
            </option>
          ))}
        </Select>
        <Select value={tier} onChange={setTier} label="Tier">
          <option value="all">All tiers</option>
          {tiers.map((value) => (
            <option key={value} value={value}>
              Tier {value}
            </option>
          ))}
        </Select>
        <Select value={source} onChange={setSource} label="Source">
          <option value="all">All sources</option>
          {sources.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </Select>
        <Select value={sort} onChange={(v) => setSort(v as Sort)} label="Sort">
          <option value="newest">Newest first</option>
          <option value="score">Highest score</option>
          <option value="reply">Latest reply</option>
          <option value="last_contacted">Last contacted</option>
          <option value="followup">Follow-up date</option>
        </Select>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
        {(
          [
            ['starred', `★ Important (${stats.starred})`],
            ['unread', `Unread replies (${stats.unread})`],
            ['due', `Due (${stats.dueToday})`],
            ['deals', `Has deal (${stats.openDeals})`],
          ] as [Quick, string][]
        ).map(([value, label]) => (
          <button
            key={value}
            onClick={() => toggleQuick(value)}
            className={`h-8 rounded-full border px-3 font-semibold transition ${
              quick.has(value) ? 'border-brand bg-brand-soft text-brand' : 'border-line text-fg-muted hover:border-brand/50'
            }`}
          >
            {label}
          </button>
        ))}
        <label className="ml-1 inline-flex items-center gap-1.5 text-fg-muted">
          <input type="checkbox" checked={hideOptOut} onChange={(e) => setHideOptOut(e.target.checked)} /> Hide do-not-contact
        </label>
        <button onClick={() => exportRows(filtered, 'filtered')} className="ml-auto font-semibold text-brand hover:underline">
          Export these {filtered.length} as CSV
        </button>
      </div>

      {checked.size > 0 && (
        <div className="sticky top-16 z-30 mt-3 flex flex-wrap items-center gap-2 rounded-2xl border border-brand/40 bg-elevated/95 p-3 text-sm shadow-card backdrop-blur">
          <span className="font-semibold">{checked.size} selected</span>
          <select
            aria-label="Set status for selected"
            disabled={bulkBusy}
            value=""
            onChange={(e) => e.target.value && bulk({ status: e.target.value as LeadStatus }, `Status → ${STATUS_LABELS[e.target.value as LeadStatus]}`)}
            className="h-9 rounded-full border border-line bg-elevated px-3 text-sm"
          >
            <option value="">Set status…</option>
            {LEAD_STATUSES.map((value) => (
              <option key={value} value={value}>
                {STATUS_LABELS[value]}
              </option>
            ))}
          </select>
          <BulkButton onClick={() => bulk({ starred: true }, 'Starred')} disabled={bulkBusy}>
            <Star className="size-3.5" /> Star
          </BulkButton>
          <BulkButton onClick={() => bulk({ next_followup: addDaysPKT(3) }, 'Follow-up in 3 days')} disabled={bulkBusy}>
            <CalendarClock className="size-3.5" /> Follow up +3d
          </BulkButton>
          <BulkButton onClick={() => bulk({ do_not_contact: true }, 'Do-not-contact')} disabled={bulkBusy}>
            <Ban className="size-3.5" /> Do not contact
          </BulkButton>
          <BulkButton onClick={() => exportRows(leads.filter((l) => checked.has(l.id)), 'selected')} disabled={bulkBusy}>
            <Download className="size-3.5" /> Export
          </BulkButton>
          <BulkButton onClick={bulkDelete} disabled={bulkBusy || readOnly} danger>
            <Trash2 className="size-3.5" /> Delete
          </BulkButton>
          <button onClick={() => setChecked(new Set())} className="ml-auto text-fg-subtle hover:text-fg" aria-label="Clear selection">
            <X className="size-4" />
          </button>
        </div>
      )}

      <div className="mt-3 overflow-hidden rounded-2xl border border-line bg-elevated">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1000px] text-left text-sm">
            <thead className="border-b border-line bg-muted/50 text-xs uppercase tracking-wide text-fg-subtle">
              <tr>
                <th className="w-10 px-3 py-3">
                  <input
                    type="checkbox"
                    aria-label="Select all shown"
                    checked={allShownChecked}
                    onChange={() =>
                      setChecked((current) => {
                        const next = new Set(current);
                        for (const lead of shown) {
                          if (allShownChecked) next.delete(lead.id);
                          else next.add(lead.id);
                        }
                        return next;
                      })
                    }
                  />
                </th>
                <th className="px-3 py-3 font-semibold">Business</th>
                <th className="px-3 py-3 font-semibold">Phone</th>
                <th className="px-3 py-3 font-semibold">Score</th>
                <th className="px-3 py-3 font-semibold">Status</th>
                <th className="px-3 py-3 font-semibold">Deal</th>
                <th className="px-3 py-3 font-semibold">Last contact</th>
                <th className="px-3 py-3 font-semibold">Follow-up</th>
                <th className="px-3 py-3 text-right font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((lead) => {
                const overdue = lead.next_followup && lead.next_followup <= today && !['won', 'lost'].includes(lead.status);
                return (
                  <tr key={lead.id} className={`border-b border-line/70 last:border-0 hover:bg-muted/30 ${checked.has(lead.id) ? 'bg-brand-soft/30' : ''}`}>
                    <td className="px-3 py-3">
                      <input type="checkbox" aria-label={`Select ${lead.name}`} checked={checked.has(lead.id)} onChange={() => toggleChecked(lead.id)} />
                    </td>
                    <td className="max-w-[280px] px-3 py-3">
                      <div className="flex items-center gap-1.5">
                        <button
                          onClick={() => quickPatch(lead, { starred: !lead.starred }, lead.starred ? 'Unstarred' : 'Starred')}
                          disabled={busyId === lead.id || readOnly}
                          aria-label={lead.starred ? `Unstar ${lead.name}` : `Star ${lead.name}`}
                          className="shrink-0 text-amber-500"
                        >
                          <Star className={`size-4 ${lead.starred ? 'fill-amber-400' : 'opacity-40 hover:opacity-100'}`} />
                        </button>
                        <button onClick={() => setSelectedId(lead.id)} className="truncate text-left font-semibold hover:text-brand">
                          {lead.name}
                        </button>
                        {(lead.unread_count || 0) > 0 && (
                          <span className="shrink-0 rounded-full bg-cta px-1.5 text-[10px] font-bold text-on-cta" title="Unread replies">
                            {lead.unread_count}
                          </span>
                        )}
                        {lead.do_not_contact && <Ban className="size-3.5 shrink-0 text-red-500" aria-label="Do not contact" />}
                      </div>
                      <p className="truncate text-xs text-fg-subtle">
                        {lead.country && <span className="mr-1" title={lead.city || lead.country}>{flagEmoji(lead.country)}</span>}
                        {[lead.business_type, lead.area || lead.city].filter(Boolean).join(' · ')}
                        {(lead.tags || []).map((tag) => (
                          <span key={tag} className="ml-1 rounded bg-muted px-1 text-[10px]">
                            #{tag}
                          </span>
                        ))}
                      </p>
                    </td>
                    <td className="whitespace-nowrap px-3 py-3 font-mono text-xs text-fg-muted">{lead.phone || lead.email}</td>
                    <td className="whitespace-nowrap px-3 py-3">
                      <span className="font-semibold">{lead.lead_score}</span>
                      <span className="mx-1 text-fg-subtle">·</span>
                      <span className="text-xs font-semibold text-fg-muted">{lead.lead_tier}</span>
                    </td>
                    <td className="px-3 py-3">
                      <select
                        aria-label={`Change status for ${lead.name}`}
                        value={lead.status}
                        disabled={busyId === lead.id || readOnly}
                        onChange={(event) =>
                          quickPatch(lead, { status: event.target.value as LeadStatus }, `Status → ${STATUS_LABELS[event.target.value as LeadStatus]}`)
                        }
                        className={`h-8 cursor-pointer rounded-full border px-2.5 text-[11px] font-semibold transition disabled:opacity-60 ${statusTone(lead.status)}`}
                      >
                        {LEAD_STATUSES.map((value) => (
                          <option key={value} value={value} disabled={value === 'queued' && lead.do_not_contact} className="bg-elevated text-fg">
                            {STATUS_LABELS[value]}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="whitespace-nowrap px-3 py-3">
                      {lead.deal_stage && lead.deal_stage !== 'none' ? (
                        <span className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold ${dealTone(lead.deal_stage)}`}>
                          {DEAL_STAGE_LABELS[lead.deal_stage]}
                          {lead.deal_value ? ` · ${formatMoney(Number(lead.deal_value), lead.deal_currency)}` : ''}
                        </span>
                      ) : (
                        <span className="text-xs text-fg-subtle">—</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-3 text-xs text-fg-muted">{lead.last_contacted || '—'}</td>
                    <td className={`whitespace-nowrap px-3 py-3 text-xs ${overdue ? 'font-semibold text-amber-600' : 'text-fg-muted'}`}>
                      {lead.next_followup || '—'}
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center justify-end gap-1">
                        {canMessage(lead) && (
                          <a
                            href={waLink(lead)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="grid size-8 place-items-center rounded-lg border border-line text-[#25d366] transition hover:border-[#25d366]"
                            aria-label={`Open WhatsApp chat with ${lead.name}`}
                          >
                            <WhatsappIcon className="size-4" />
                          </a>
                        )}
                        {whatsappEnabled && phoneDigits(lead.phone) && (
                          <a
                            href={`/admin/inbox?key=wa:${phoneDigits(lead.phone)}`}
                            className="grid size-8 place-items-center rounded-lg border border-line text-fg-muted transition hover:border-brand hover:text-brand"
                            aria-label={`Open inbox thread with ${lead.name}`}
                          >
                            <Inbox className="size-4" />
                          </a>
                        )}
                        <button
                          type="button"
                          onClick={() => setSelectedId(lead.id)}
                          className="h-8 rounded-lg border border-line px-2.5 text-xs font-semibold text-fg-muted transition hover:border-brand hover:text-brand"
                        >
                          Details
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {shown.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-4 py-12 text-center text-sm text-fg-muted">
                    {leads.length ? 'No leads match these filters.' : 'No leads yet — import a spreadsheet or add one by hand.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {filtered.length > visible && (
          <div className="border-t border-line px-4 py-3 text-center">
            <button type="button" onClick={() => setVisible((value) => value + PAGE)} className="text-sm font-semibold text-brand hover:underline">
              Show more ({filtered.length - visible} remaining)
            </button>
          </div>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-xs text-fg-subtle">
        <span>
          Showing {shown.length} of {filtered.length} filtered leads
        </span>
        <a href="/admin/docs" className="hover:text-brand">
          Read the outreach playbook →
        </a>
      </div>

      {selected && (
        <LeadDrawer
          lead={selected}
          whatsappEnabled={whatsappEnabled}
          readOnly={readOnly}
          onClose={() => setSelectedId(null)}
          onSaved={(lead, message) => {
            replaceLead(lead);
            if (message) setToast(message);
          }}
          onDeleted={(id) => {
            setLeads((rows) => rows.filter((row) => row.id !== id));
            setSelectedId(null);
            setToast('Lead deleted');
          }}
        />
      )}

      {dialog === 'import' && (
        <ImportDialog
          onClose={() => setDialog(null)}
          onImported={(summary) => {
            setToast(`Imported: ${summary.inserted} added, ${summary.updated} updated`);
            void reload();
          }}
        />
      )}
      {dialog === 'add' && (
        <AddLeadDialog
          onClose={() => setDialog(null)}
          onCreated={(lead) => {
            setLeads((rows) => [lead, ...rows]);
            setDialog(null);
            setSelectedId(lead.id);
            setToast('Lead added');
          }}
        />
      )}

      <Toast message={toast} />
    </div>
  );
}

function Select({
  value,
  onChange,
  label,
  children,
}: {
  value: string;
  onChange: (value: string) => void;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-10 rounded-full border border-line bg-elevated px-3 text-sm"
    >
      {children}
    </select>
  );
}

function BulkButton({
  children,
  onClick,
  disabled,
  danger,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex h-9 items-center gap-1.5 rounded-full border border-line px-3 font-semibold text-fg-muted transition disabled:opacity-50 ${
        danger ? 'hover:border-red-400 hover:text-red-500' : 'hover:border-brand hover:text-brand'
      }`}
    >
      {children}
    </button>
  );
}

function StorageNotice({ mode }: { mode: StorageMode }) {
  if (mode === 'supabase') {
    return (
      <p className="mt-3 inline-flex items-center gap-1.5 text-xs text-fg-subtle">
        <span className="size-1.5 rounded-full bg-emerald-500" /> Synced to Supabase.
      </p>
    );
  }
  if (mode === 'file') {
    return (
      <Notice>
        Local file storage (<code>.data/*.json</code>). Changes work in development but won&apos;t persist on Netlify or Vercel — add
        the Supabase env vars to go live.
      </Notice>
    );
  }
  return (
    <Notice>
      No database connected, so the CRM is empty and read-only. Add <code>SUPABASE_URL</code> and{' '}
      <code>SUPABASE_SERVICE_ROLE_KEY</code>, run the migrations in <code>supabase/migrations/</code>, then redeploy.
    </Notice>
  );
}
