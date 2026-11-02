'use client';

import { useMemo, useState } from 'react';
import { Briefcase, CalendarClock, MessageCircle, Plus, Star } from 'lucide-react';
import {
  DEAL_STAGES,
  DEAL_STAGE_LABELS,
  WON_DEAL_STAGES,
  formatMoney,
  timeAgo,
  todayPKT,
  type DealStage,
  type Lead,
} from '@/lib/lead-types';
import LeadDrawer from '@/components/admin/LeadDrawer';
import { leadsApi } from '@/components/admin/client-api';
import { ErrorBanner, StatCard, Toast, useNotice } from '@/components/admin/ui';

const BOARD_STAGES = DEAL_STAGES.filter((stage) => stage !== 'none');

const STAGE_ACCENT: Record<DealStage, string> = {
  none: 'bg-muted',
  discovery: 'bg-sky-400',
  proposal: 'bg-sky-500',
  negotiation: 'bg-indigo-500',
  in_progress: 'bg-violet-500',
  review: 'bg-fuchsia-500',
  delivered: 'bg-emerald-500',
  on_hold: 'bg-amber-500',
};

/** Kanban for work that is past "interested": proposals, active projects, delivery. */
export default function DealsBoard({
  initialLeads,
  whatsappEnabled,
  readOnly,
}: {
  initialLeads: Lead[];
  whatsappEnabled: boolean;
  readOnly: boolean;
}) {
  const [leads, setLeads] = useState(initialLeads);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dragging, setDragging] = useState<string | null>(null);
  const [over, setOver] = useState<DealStage | null>(null);
  const { toast, setToast, error, setError, fail } = useNotice();

  const columns = useMemo(() => {
    const map = new Map<DealStage, Lead[]>(BOARD_STAGES.map((stage) => [stage, []]));
    for (const lead of leads) {
      if (lead.deal_stage && lead.deal_stage !== 'none') map.get(lead.deal_stage)?.push(lead);
    }
    for (const list of map.values()) list.sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
    return map;
  }, [leads]);

  const candidates = useMemo(
    () =>
      leads
        .filter(
          (lead) =>
            (!lead.deal_stage || lead.deal_stage === 'none') &&
            (lead.status === 'interested' || lead.status === 'replied' || lead.starred) &&
            !['won', 'lost'].includes(lead.status),
        )
        .sort((a, b) => (b.last_inbound_at || b.updated_at).localeCompare(a.last_inbound_at || a.updated_at))
        .slice(0, 30),
    [leads],
  );

  const totals = useMemo(() => {
    const open = leads.filter((l) => l.deal_stage && !['none', 'delivered'].includes(l.deal_stage));
    const won = leads.filter((l) => l.deal_stage && WON_DEAL_STAGES.includes(l.deal_stage));
    const sum = (rows: Lead[]) => rows.reduce((acc, l) => acc + (Number(l.deal_value) || 0), 0);
    return {
      open: open.length,
      openValue: sum(open),
      active: (columns.get('in_progress')?.length || 0) + (columns.get('review')?.length || 0),
      wonValue: sum(won),
    };
  }, [leads, columns]);

  async function move(lead: Lead, stage: DealStage) {
    if (readOnly || lead.deal_stage === stage) return;
    const previous = lead;
    // Optimistic: move the card now, roll back if the server refuses.
    setLeads((rows) => rows.map((row) => (row.id === lead.id ? { ...row, deal_stage: stage } : row)));
    setError('');
    try {
      const updated = await leadsApi.patch(lead.id, { deal_stage: stage });
      setLeads((rows) => rows.map((row) => (row.id === lead.id ? updated : row)));
      setToast(`${lead.name} → ${DEAL_STAGE_LABELS[stage]}`);
    } catch (err) {
      setLeads((rows) => rows.map((row) => (row.id === lead.id ? previous : row)));
      fail(err);
    }
  }

  const selected = leads.find((lead) => lead.id === selectedId) || null;
  const today = todayPKT();

  return (
    <div>
      <p className="eyebrow">Deals</p>
      <h1 className="mt-2 text-3xl font-bold">Work in progress</h1>
      <p className="mt-1 text-sm text-fg-muted">Drag cards between stages, or use the stage menu on each card.</p>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard icon={Briefcase} label="Open deals" value={totals.open} />
        <StatCard icon={Briefcase} label="Pipeline value" value={formatMoney(totals.openValue)} />
        <StatCard icon={CalendarClock} label="Projects in progress" value={totals.active} />
        <StatCard icon={Star} label="Won value" value={formatMoney(totals.wonValue)} />
      </div>

      <ErrorBanner message={error} onDismiss={() => setError('')} />

      <div className="mt-6 flex gap-3 overflow-x-auto pb-4">
        <section className="w-72 shrink-0 rounded-2xl border border-dashed border-line bg-muted/30 p-3">
          <h2 className="text-sm font-bold">Ready to qualify</h2>
          <p className="text-[11px] text-fg-subtle">Interested, replied or starred — no deal yet</p>
          <div className="mt-3 space-y-2">
            {candidates.map((lead) => (
              <div key={lead.id} className="rounded-xl border border-line bg-elevated p-3 text-sm">
                <button onClick={() => setSelectedId(lead.id)} className="block truncate text-left font-semibold hover:text-brand">
                  {lead.name}
                </button>
                <p className="truncate text-[11px] text-fg-subtle">{[lead.business_type, lead.area].filter(Boolean).join(' · ')}</p>
                <button
                  onClick={() => move(lead, 'discovery')}
                  disabled={readOnly}
                  className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-brand disabled:opacity-50"
                >
                  <Plus className="size-3" /> Start deal
                </button>
              </div>
            ))}
            {!candidates.length && <p className="text-xs text-fg-muted">No interested leads waiting.</p>}
          </div>
        </section>

        {BOARD_STAGES.map((stage) => {
          const cards = columns.get(stage) || [];
          const value = cards.reduce((sum, lead) => sum + (Number(lead.deal_value) || 0), 0);
          return (
            <section
              key={stage}
              onDragOver={(event) => {
                event.preventDefault();
                setOver(stage);
              }}
              onDragLeave={() => setOver((current) => (current === stage ? null : current))}
              onDrop={(event) => {
                event.preventDefault();
                setOver(null);
                const lead = leads.find((row) => row.id === dragging);
                if (lead) void move(lead, stage);
              }}
              className={`w-72 shrink-0 rounded-2xl border bg-elevated p-3 transition ${over === stage ? 'border-brand ring-2 ring-brand/20' : 'border-line'}`}
            >
              <div className="flex items-center gap-2">
                <span className={`size-2.5 rounded-full ${STAGE_ACCENT[stage]}`} />
                <h2 className="text-sm font-bold">{DEAL_STAGE_LABELS[stage]}</h2>
                <span className="ml-auto rounded-full bg-muted px-2 text-[11px] font-semibold text-fg-muted">{cards.length}</span>
              </div>
              <p className="mt-0.5 text-[11px] text-fg-subtle">{value ? formatMoney(value) : 'No value set'}</p>
              <div className="mt-3 min-h-16 space-y-2">
                {cards.map((lead) => (
                  <article
                    key={lead.id}
                    draggable={!readOnly}
                    onDragStart={() => setDragging(lead.id)}
                    onDragEnd={() => setDragging(null)}
                    className={`cursor-grab rounded-xl border border-line bg-bg p-3 text-sm shadow-sm active:cursor-grabbing ${dragging === lead.id ? 'opacity-50' : ''}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <button onClick={() => setSelectedId(lead.id)} className="min-w-0 truncate text-left font-semibold hover:text-brand">
                        {lead.starred && <Star className="mr-1 inline size-3 fill-amber-400 text-amber-500" />}
                        {lead.name}
                      </button>
                      {(lead.unread_count || 0) > 0 && (
                        <span className="inline-flex shrink-0 items-center gap-0.5 rounded-full bg-cta px-1.5 text-[10px] font-bold text-on-cta">
                          <MessageCircle className="size-2.5" /> {lead.unread_count}
                        </span>
                      )}
                    </div>
                    <p className="mt-0.5 truncate text-[11px] text-fg-subtle">{[lead.business_type, lead.area].filter(Boolean).join(' · ')}</p>
                    <div className="mt-2 flex items-center justify-between gap-2 text-[11px]">
                      <span className="font-semibold">{lead.deal_value ? formatMoney(Number(lead.deal_value), lead.deal_currency) : '—'}</span>
                      <span className={lead.next_followup && lead.next_followup <= today ? 'font-semibold text-amber-600' : 'text-fg-subtle'}>
                        {lead.next_followup ? `Next: ${lead.next_followup}` : `Updated ${timeAgo(lead.updated_at)}`}
                      </span>
                    </div>
                    <select
                      aria-label={`Move ${lead.name} to stage`}
                      value={lead.deal_stage}
                      disabled={readOnly}
                      onChange={(event) => move(lead, event.target.value as DealStage)}
                      className="mt-2 h-7 w-full rounded-lg border border-line bg-elevated px-2 text-[11px]"
                    >
                      {DEAL_STAGES.map((value) => (
                        <option key={value} value={value}>
                          {value === 'none' ? 'Remove from board' : DEAL_STAGE_LABELS[value]}
                        </option>
                      ))}
                    </select>
                  </article>
                ))}
              </div>
            </section>
          );
        })}
      </div>

      {selected && (
        <LeadDrawer
          lead={selected}
          whatsappEnabled={whatsappEnabled}
          readOnly={readOnly}
          onClose={() => setSelectedId(null)}
          onSaved={(lead, message) => {
            setLeads((rows) => rows.map((row) => (row.id === lead.id ? lead : row)));
            if (message) setToast(message);
          }}
          onDeleted={(id) => {
            setLeads((rows) => rows.filter((row) => row.id !== id));
            setSelectedId(null);
          }}
        />
      )}
      <Toast message={toast} />
    </div>
  );
}
