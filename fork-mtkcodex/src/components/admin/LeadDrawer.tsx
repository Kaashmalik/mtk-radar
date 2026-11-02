'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Ban,
  Briefcase,
  CalendarClock,
  Copy,
  ExternalLink,
  History,
  Inbox,
  Mail,
  MapPin,
  MessageCircle,
  MessageSquareText,
  Pencil,
  RefreshCw,
  Save,
  Send,
  Star,
  StickyNote,
  Trash2,
  UserPlus,
  X,
} from 'lucide-react';
import {
  DEAL_STAGES,
  DEAL_STAGE_LABELS,
  LEAD_STATUSES,
  PREFERRED_CHANNEL_LABELS,
  STATUS_LABELS,
  addDaysPKT,
  flagEmoji,
  localTime,
  placeLabel,
  type PreferredChannel,
  canMessage,
  phoneDigits,
  timeAgo,
  waLink,
  type ActivityKind,
  type DealStage,
  type Lead,
  type LeadActivity,
  type LeadStatus,
} from '@/lib/lead-types';
import { WhatsappIcon } from '@/components/ui/BrandIcons';
import { leadsApi, type LeadPatchBody } from '@/components/admin/client-api';
import { Field, Metric, inputClass, primaryButtonClass, textareaClass } from '@/components/admin/ui';

type Draft = {
  name: string;
  business_type: string;
  area: string;
  phone: string;
  email: string;
  website: string;
  status: LeadStatus;
  next_followup: string;
  message: string;
  notes: string;
  do_not_contact: boolean;
  starred: boolean;
  tags: string;
  deal_stage: DealStage;
  deal_value: string;
};

function toDraft(lead: Lead): Draft {
  return {
    name: lead.name,
    business_type: lead.business_type || '',
    area: lead.area || '',
    phone: lead.phone || '',
    email: lead.email || '',
    website: lead.website || '',
    status: lead.status,
    next_followup: lead.next_followup || '',
    message: lead.message || '',
    notes: lead.notes || '',
    do_not_contact: Boolean(lead.do_not_contact),
    starred: Boolean(lead.starred),
    tags: (lead.tags || []).join(', '),
    deal_stage: lead.deal_stage || 'none',
    deal_value: lead.deal_value === null || lead.deal_value === undefined ? '' : String(lead.deal_value),
  };
}

/** Only the fields that changed, in the API's shape. */
function diff(lead: Lead, draft: Draft): LeadPatchBody {
  const base = toDraft(lead);
  const patch: LeadPatchBody = {};
  for (const key of ['name', 'business_type', 'area', 'phone', 'email', 'website', 'message', 'notes'] as const) {
    if (draft[key] !== base[key]) patch[key] = draft[key];
  }
  if (draft.status !== base.status) patch.status = draft.status;
  if (draft.next_followup !== base.next_followup) patch.next_followup = draft.next_followup || null;
  if (draft.do_not_contact !== base.do_not_contact) patch.do_not_contact = draft.do_not_contact;
  if (draft.starred !== base.starred) patch.starred = draft.starred;
  if (draft.deal_stage !== base.deal_stage) patch.deal_stage = draft.deal_stage;
  if (draft.deal_value !== base.deal_value) patch.deal_value = draft.deal_value === '' ? null : Number(draft.deal_value);
  const tags = draft.tags
    .split(',')
    .map((tag) => tag.trim().toLowerCase())
    .filter(Boolean);
  if (tags.join(',') !== (lead.tags || []).join(',')) patch.tags = tags;
  return patch;
}

const ACTIVITY_ICONS: Record<ActivityKind, React.ComponentType<{ className?: string }>> = {
  created: UserPlus,
  import: RefreshCw,
  status: History,
  note: StickyNote,
  followup: CalendarClock,
  deal: Briefcase,
  message_out: Send,
  message_in: MessageCircle,
  opt_out: Ban,
  edit: Pencil,
};

export default function LeadDrawer({
  lead,
  whatsappEnabled,
  readOnly,
  onClose,
  onSaved,
  onDeleted,
}: {
  lead: Lead;
  whatsappEnabled: boolean;
  readOnly: boolean;
  onClose: () => void;
  onSaved: (lead: Lead, message?: string) => void;
  onDeleted: (id: string) => void;
}) {
  const [tab, setTab] = useState<'details' | 'timeline'>('details');
  const [draft, setDraft] = useState<Draft>(() => toDraft(lead));
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [activities, setActivities] = useState<LeadActivity[] | null>(null);
  const [activityError, setActivityError] = useState('');

  // Re-sync when another action (inbox, bulk edit) replaced the lead.
  useEffect(() => setDraft(toDraft(lead)), [lead]);

  const loadActivities = useCallback(async () => {
    try {
      const data = await leadsApi.activities(lead.id);
      setActivities(data.activities);
      setActivityError(data.error || '');
    } catch (err) {
      setActivityError(err instanceof Error ? err.message : 'Could not load the timeline');
      setActivities([]);
    }
  }, [lead.id]);

  useEffect(() => {
    void loadActivities();
  }, [loadActivities, lead.updated_at]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const patch = useMemo(() => diff(lead, draft), [lead, draft]);
  const dirty = Object.keys(patch).length > 0;
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((current) => ({ ...current, [key]: value }));

  async function save(extra: LeadPatchBody = {}, message = 'Saved') {
    const body = { ...patch, ...extra };
    if (!Object.keys(body).length) return;
    setSaving(true);
    setError('');
    try {
      const updated = await leadsApi.patch(lead.id, body);
      onSaved(updated, message);
      setNote('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save');
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!window.confirm(`Delete ${lead.name} and its history? This cannot be undone.`)) return;
    setSaving(true);
    try {
      await leadsApi.remove([lead.id]);
      onDeleted(lead.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete');
      setSaving(false);
    }
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      onSaved(lead, 'Message copied');
    } catch {
      setError('Copy failed — select the text manually.');
    }
  }

  const messageable = canMessage(lead);
  const digits = phoneDigits(lead.phone);

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button className="absolute inset-0 bg-black/40" onClick={onClose} aria-label="Close details" />
      <aside className="relative flex h-full w-full max-w-xl flex-col border-l border-line bg-elevated shadow-float">
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => save({ starred: !lead.starred }, lead.starred ? 'Removed star' : 'Starred')}
                disabled={readOnly || saving}
                aria-label={lead.starred ? 'Unstar lead' : 'Star lead'}
                className="text-amber-500 disabled:opacity-50"
              >
                <Star className={`size-5 ${lead.starred ? 'fill-amber-400' : ''}`} />
              </button>
              <h2 className="truncate text-lg font-bold">{lead.name}</h2>
            </div>
            <p className="mt-0.5 text-xs text-fg-subtle">
              {[lead.business_type, lead.area].filter(Boolean).join(' · ') || 'No category'} · source {lead.source || 'scraper'}
            </p>
            {lead.do_not_contact && (
              <p className="mt-2 inline-flex items-center gap-1 rounded-full border border-red-500/30 bg-red-500/10 px-2 py-0.5 text-[11px] font-semibold text-red-500">
                <Ban className="size-3" /> Do not contact
              </p>
            )}
          </div>
          <button onClick={onClose} className="rounded-lg border border-line p-2 text-fg-muted hover:text-fg" aria-label="Close">
            <X className="size-4" />
          </button>
        </div>

        <div className="flex gap-1 border-b border-line px-5">
          {(
            [
              ['details', 'Details'],
              ['timeline', `Timeline${activities ? ` (${activities.length})` : ''}`],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              onClick={() => setTab(value)}
              className={`-mb-px border-b-2 px-3 py-2.5 text-sm font-semibold transition ${
                tab === value ? 'border-brand text-brand' : 'border-transparent text-fg-muted hover:text-fg'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto">
          {tab === 'details' ? (
            <div className="space-y-5 px-5 py-5">
              <div className="flex flex-wrap gap-2 text-xs">
                {lead.phone && (
                  <a
                    href={`tel:${lead.phone}`}
                    className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 font-semibold text-fg-muted hover:border-brand hover:text-brand"
                  >
                    {lead.phone}
                  </a>
                )}
                {messageable && (
                  <a
                    href={waLink(lead)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 font-semibold text-[#1da851] hover:border-[#25d366]"
                  >
                    <WhatsappIcon className="size-3.5" /> WhatsApp
                  </a>
                )}
                {lead.email && (
                  <a
                    href={`/admin/inbox?key=${encodeURIComponent(`email:${lead.email.toLowerCase()}`)}`}
                    className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 font-semibold text-fg-muted hover:border-brand hover:text-brand"
                  >
                    <Mail className="size-3.5" /> Email in inbox
                  </a>
                )}
                {whatsappEnabled && digits && (
                  <a
                    href={`/admin/inbox?key=wa:${digits}`}
                    className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 font-semibold text-fg-muted hover:border-brand hover:text-brand"
                  >
                    <Inbox className="size-3.5" /> Chat in inbox
                    {(lead.unread_count || 0) > 0 && (
                      <span className="rounded-full bg-cta px-1.5 text-[10px] text-on-cta">{lead.unread_count}</span>
                    )}
                  </a>
                )}
                {lead.email && (
                  <a
                    href={`mailto:${lead.email}`}
                    className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 font-semibold text-fg-muted hover:border-brand hover:text-brand"
                  >
                    {lead.email}
                  </a>
                )}
                {/^https:\/\/(www\.)?google\.[a-z.]+\/maps/.test(lead.google_maps_url || '') && (
                  <a
                    href={lead.google_maps_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 font-semibold text-fg-muted hover:border-brand hover:text-brand"
                  >
                    <ExternalLink className="size-3.5" /> Maps
                  </a>
                )}
              </div>

              {(lead.city || lead.country || lead.timezone || lead.preferred_channel) && (
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl border border-line bg-muted/40 px-3 py-2 text-xs text-fg-muted">
                  {(lead.city || lead.country) && (
                    <span className="inline-flex items-center gap-1">
                      <MapPin className="size-3.5" /> {flagEmoji(lead.country || '')}{' '}
                      {placeLabel({ city: lead.city, region: lead.region, country: lead.country })}
                    </span>
                  )}
                  {localTime(lead.timezone) && (
                    <span>
                      Their time <strong className="text-fg">{localTime(lead.timezone)}</strong>
                    </span>
                  )}
                  {lead.preferred_channel && (
                    <span>
                      Prefers <strong className="text-fg">{PREFERRED_CHANNEL_LABELS[lead.preferred_channel as PreferredChannel] || lead.preferred_channel}</strong>
                    </span>
                  )}
                </div>
              )}

              <div className="grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
                <Metric label="Score" value={`${lead.lead_score} / ${lead.lead_tier}`} />
                <Metric label="Scenario" value={lead.scenario || '—'} />
                <Metric label="Last contact" value={lead.last_contacted || '—'} />
                <Metric label="Last reply" value={lead.last_inbound_at ? timeAgo(lead.last_inbound_at) : '—'} />
              </div>

              <section className="grid gap-3 sm:grid-cols-2">
                <Field label="Status">
                  <select
                    value={draft.status}
                    onChange={(event) => set('status', event.target.value as LeadStatus)}
                    className={inputClass}
                  >
                    {LEAD_STATUSES.map((value) => (
                      <option key={value} value={value} disabled={value === 'queued' && draft.do_not_contact}>
                        {STATUS_LABELS[value]}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Next follow-up">
                  <input
                    type="date"
                    value={draft.next_followup}
                    onChange={(event) => set('next_followup', event.target.value)}
                    className={inputClass}
                  />
                </Field>
                <div className="-mt-1 flex flex-wrap gap-1.5 sm:col-span-2">
                  {[
                    ['Tomorrow', 1],
                    ['+2 days', 2],
                    ['+3 days', 3],
                    ['+1 week', 7],
                  ].map(([label, days]) => (
                    <button
                      key={label}
                      type="button"
                      onClick={() => set('next_followup', addDaysPKT(Number(days)))}
                      className="rounded-full border border-line px-2.5 py-1 text-[11px] font-semibold text-fg-muted hover:border-brand hover:text-brand"
                    >
                      {label}
                    </button>
                  ))}
                  {draft.next_followup && (
                    <button
                      type="button"
                      onClick={() => set('next_followup', '')}
                      className="rounded-full px-2.5 py-1 text-[11px] font-semibold text-fg-subtle hover:text-red-500"
                    >
                      Clear
                    </button>
                  )}
                </div>
              </section>

              <section className="rounded-xl border border-line p-4">
                <h3 className="flex items-center gap-2 text-sm font-bold">
                  <Briefcase className="size-4 text-brand" /> Deal
                </h3>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <Field label="Stage">
                    <select
                      value={draft.deal_stage}
                      onChange={(event) => set('deal_stage', event.target.value as DealStage)}
                      className={inputClass}
                    >
                      {DEAL_STAGES.map((stage) => (
                        <option key={stage} value={stage}>
                          {DEAL_STAGE_LABELS[stage]}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label={`Value (${lead.deal_currency || 'PKR'})`}>
                    <input
                      type="number"
                      min={0}
                      step={1000}
                      inputMode="numeric"
                      value={draft.deal_value}
                      onChange={(event) => set('deal_value', event.target.value)}
                      placeholder="e.g. 150000"
                      className={inputClass}
                    />
                  </Field>
                </div>
                <p className="mt-2 text-[11px] text-fg-subtle">
                  Moving a deal to discovery/proposal marks the lead Interested; work in progress or later marks it Won.
                </p>
              </section>

              <Field label="Message sent / to send">
                <textarea
                  value={draft.message}
                  onChange={(event) => set('message', event.target.value)}
                  rows={6}
                  className={textareaClass}
                />
              </Field>
              <div className="-mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => copy(draft.message)}
                  className="inline-flex h-9 items-center gap-1.5 rounded-full border border-line px-3 text-xs font-semibold text-fg-muted hover:border-brand hover:text-brand"
                >
                  <Copy className="size-3.5" /> Copy message
                </button>
              </div>

              <section>
                <Field label="Add a note" hint="Dated and added to the timeline.">
                  <div className="flex gap-2">
                    <input
                      value={note}
                      onChange={(event) => setNote(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' && note.trim()) {
                          event.preventDefault();
                          void save({ append_note: note.trim() }, 'Note added');
                        }
                      }}
                      placeholder="Spoke to the owner, wants a quote by Friday…"
                      className={inputClass}
                    />
                    <button
                      type="button"
                      disabled={!note.trim() || saving || readOnly}
                      onClick={() => save({ append_note: note.trim() }, 'Note added')}
                      className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-xl border border-line px-3 text-sm font-semibold text-fg-muted hover:border-brand hover:text-brand disabled:opacity-50"
                    >
                      <MessageSquareText className="size-4" /> Add
                    </button>
                  </div>
                </Field>
              </section>

              <Field label="Notes">
                <textarea
                  value={draft.notes}
                  onChange={(event) => set('notes', event.target.value)}
                  rows={4}
                  placeholder="Contact person, reply summary, next step…"
                  className={textareaClass}
                />
              </Field>

              <Field label="Tags" hint="Comma separated, e.g. hot, dental, referral">
                <input value={draft.tags} onChange={(event) => set('tags', event.target.value)} className={inputClass} />
              </Field>

              <details className="rounded-xl border border-line p-4">
                <summary className="cursor-pointer text-sm font-bold">Business profile</summary>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <Field label="Name">
                    <input value={draft.name} onChange={(event) => set('name', event.target.value)} className={inputClass} />
                  </Field>
                  <Field label="Phone">
                    <input value={draft.phone} onChange={(event) => set('phone', event.target.value)} className={inputClass} />
                  </Field>
                  <Field label="Email">
                    <input
                      type="email"
                      value={draft.email}
                      onChange={(event) => set('email', event.target.value)}
                      className={inputClass}
                    />
                  </Field>
                  <Field label="Website">
                    <input value={draft.website} onChange={(event) => set('website', event.target.value)} className={inputClass} />
                  </Field>
                  <Field label="Business type">
                    <input
                      value={draft.business_type}
                      onChange={(event) => set('business_type', event.target.value)}
                      className={inputClass}
                    />
                  </Field>
                  <Field label="Area">
                    <input value={draft.area} onChange={(event) => set('area', event.target.value)} className={inputClass} />
                  </Field>
                </div>
                {lead.recommended_pitch && (
                  <p className="mt-3 rounded-lg bg-muted/50 p-3 text-xs leading-relaxed text-fg-muted">
                    <strong>Pitch:</strong> {lead.recommended_pitch}
                  </p>
                )}
              </details>

              <label className="flex items-start gap-3 rounded-xl border border-line bg-muted/40 p-3 text-sm">
                <input
                  type="checkbox"
                  checked={draft.do_not_contact}
                  onChange={(event) => set('do_not_contact', event.target.checked)}
                  className="mt-0.5 size-4 rounded border-line"
                />
                <span>
                  <span className="font-semibold">Do not contact</span>
                  <span className="block text-xs text-fg-subtle">
                    Blocks queueing and sending everywhere. Set automatically when someone replies STOP.
                  </span>
                </span>
              </label>

              <button
                type="button"
                onClick={remove}
                disabled={saving || readOnly}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-fg-subtle hover:text-red-500 disabled:opacity-50"
              >
                <Trash2 className="size-3.5" /> Delete lead
              </button>
            </div>
          ) : (
            <Timeline activities={activities} error={activityError} onRefresh={loadActivities} />
          )}
        </div>

        {error && <p className="border-t border-red-500/30 bg-red-500/10 px-5 py-2 text-sm text-red-500">{error}</p>}

        <div className="flex gap-2 border-t border-line bg-elevated px-5 py-4">
          <button
            type="button"
            onClick={() => save()}
            disabled={saving || !dirty || readOnly}
            className={`${primaryButtonClass} flex-1`}
          >
            {saving ? <RefreshCw className="size-4 animate-spin" /> : <Save className="size-4" />}
            {saving ? 'Saving…' : dirty ? 'Save changes' : 'No changes'}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-10 items-center justify-center rounded-full border border-line px-4 text-sm font-semibold text-fg-muted hover:text-fg"
          >
            Close
          </button>
        </div>
      </aside>
    </div>
  );
}

function Timeline({
  activities,
  error,
  onRefresh,
}: {
  activities: LeadActivity[] | null;
  error: string;
  onRefresh: () => void;
}) {
  if (!activities) return <p className="px-5 py-8 text-center text-sm text-fg-muted">Loading timeline…</p>;
  return (
    <div className="px-5 py-5">
      <div className="mb-4 flex items-center justify-between">
        <p className="text-xs text-fg-subtle">Every send, reply, status move, note and deal change.</p>
        <button onClick={onRefresh} className="inline-flex items-center gap-1 text-xs font-semibold text-brand">
          <RefreshCw className="size-3" /> Refresh
        </button>
      </div>
      {error && (
        <p className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-400">
          Timeline unavailable — run <code>supabase/migrations/0004_crm_v2.sql</code>. ({error})
        </p>
      )}
      {activities.length === 0 && !error && <p className="text-sm text-fg-muted">No activity recorded yet.</p>}
      <ol className="relative space-y-4 border-l border-line pl-5">
        {activities.map((item) => {
          const Icon = ACTIVITY_ICONS[item.kind] || History;
          const inbound = item.kind === 'message_in';
          return (
            <li key={item.id} className="relative">
              <span
                className={`absolute -left-[31px] grid size-6 place-items-center rounded-full border border-line ${
                  inbound ? 'bg-sky-500/15 text-sky-500' : item.kind === 'message_out' ? 'bg-brand-soft text-brand' : 'bg-elevated text-fg-subtle'
                }`}
              >
                <Icon className="size-3" />
              </span>
              <p className={`text-sm ${inbound ? 'rounded-lg bg-sky-500/10 px-2.5 py-1.5' : ''}`}>{item.summary}</p>
              <p className="mt-0.5 text-[11px] text-fg-subtle" title={new Date(item.created_at).toLocaleString()}>
                {new Date(item.created_at).toLocaleString('en-PK', { dateStyle: 'medium', timeStyle: 'short' })} ·{' '}
                {timeAgo(item.created_at)}
              </p>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
