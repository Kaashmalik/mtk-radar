'use client';

import { useMemo } from 'react';
import { CalendarClock, Flame, MessageCircle, Send } from 'lucide-react';
import {
  STATUS_LABELS,
  addDaysPKT,
  statusTone,
  timeAgo,
  todayPKT,
  type ActivityKind,
  type Lead,
} from '@/lib/lead-types';

export type ActivityPoint = { kind: ActivityKind; created_at: string };
export type FeedItem = { id: string | number; lead_id: string; kind: ActivityKind; summary: string; created_at: string; lead_name: string };

const DAYS = 14;

/** Daily sends vs. replies for the last two weeks, plus today's to-do lists. */
export default function TodayPanel({
  leads,
  points,
  feed,
  onOpen,
}: {
  leads: Lead[];
  points: ActivityPoint[];
  feed: FeedItem[];
  onOpen: (id: string) => void;
}) {
  const today = todayPKT();

  const series = useMemo(() => {
    const days = Array.from({ length: DAYS }, (_, i) => addDaysPKT(i - (DAYS - 1)));
    const sent = new Map(days.map((day) => [day, 0]));
    const replies = new Map(days.map((day) => [day, 0]));
    for (const point of points) {
      const day = todayPKT(new Date(point.created_at));
      if (point.kind === 'message_out' && sent.has(day)) sent.set(day, (sent.get(day) || 0) + 1);
      if (point.kind === 'message_in' && replies.has(day)) replies.set(day, (replies.get(day) || 0) + 1);
    }
    return days.map((day) => ({ day, sent: sent.get(day) || 0, replies: replies.get(day) || 0 }));
  }, [points]);

  const max = Math.max(1, ...series.map((d) => Math.max(d.sent, d.replies)));
  const sentToday = series.at(-1)?.sent || 0;
  const sentWeek = series.slice(-7).reduce((sum, d) => sum + d.sent, 0);
  const repliesWeek = series.slice(-7).reduce((sum, d) => sum + d.replies, 0);

  const due = useMemo(
    () =>
      leads
        .filter((l) => l.next_followup && l.next_followup <= today && !['won', 'lost'].includes(l.status) && !l.do_not_contact)
        .sort((a, b) => (a.next_followup || '').localeCompare(b.next_followup || ''))
        .slice(0, 6),
    [leads, today],
  );

  const hot = useMemo(
    () =>
      leads
        .filter((l) => (l.starred || l.status === 'interested' || (l.unread_count || 0) > 0) && !['won', 'lost'].includes(l.status))
        .sort((a, b) => (b.unread_count || 0) - (a.unread_count || 0) || (b.last_inbound_at || b.updated_at).localeCompare(a.last_inbound_at || a.updated_at))
        .slice(0, 6),
    [leads],
  );

  return (
    <div className="mt-6 grid gap-4 lg:grid-cols-3">
      <section className="card p-4 lg:col-span-1">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-sm font-bold">Messages, last 14 days</h2>
            <p className="mt-0.5 text-xs text-fg-subtle">
              <span className="font-semibold text-fg">{sentToday}</span> sent today · {sentWeek} this week · {repliesWeek} replies
            </p>
          </div>
          <Send className="size-4 text-brand" />
        </div>
        <div className="mt-4 flex h-28 items-end gap-1" role="img" aria-label={`Messages sent per day; ${sentToday} today`}>
          {series.map((d) => (
            <div key={d.day} className="group relative flex flex-1 items-end gap-px" title={`${d.day}: ${d.sent} sent, ${d.replies} replies`}>
              <span className="w-1/2 rounded-t bg-cta" style={{ height: `${(d.sent / max) * 100}%`, minHeight: d.sent ? 3 : 0 }} />
              <span className="w-1/2 rounded-t bg-sky-500/70" style={{ height: `${(d.replies / max) * 100}%`, minHeight: d.replies ? 3 : 0 }} />
            </div>
          ))}
        </div>
        <div className="mt-2 flex items-center gap-3 text-[11px] text-fg-subtle">
          <span className="inline-flex items-center gap-1">
            <span className="size-2 rounded-sm bg-cta" /> Sent
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="size-2 rounded-sm bg-sky-500/70" /> Replies
          </span>
          <span className="ml-auto">{sentToday >= 20 ? 'Daily limit reached — pause sends' : `${Math.max(0, 20 - sentToday)} sends left today (~20 safe)`}</span>
        </div>
      </section>

      <section className="card p-4">
        <h2 className="flex items-center gap-2 text-sm font-bold">
          <CalendarClock className="size-4 text-amber-500" /> Follow-ups due
        </h2>
        <LeadList leads={due} empty="Nothing due. Nice." detail={(l) => (l.next_followup === today ? 'today' : `since ${l.next_followup}`)} onOpen={onOpen} />
      </section>

      <section className="card p-4">
        <h2 className="flex items-center gap-2 text-sm font-bold">
          <Flame className="size-4 text-orange-500" /> Hot leads
        </h2>
        <LeadList
          leads={hot}
          empty="Star leads or mark them Interested to see them here."
          detail={(l) => ((l.unread_count || 0) > 0 ? `${l.unread_count} unread` : l.last_inbound_at ? `replied ${timeAgo(l.last_inbound_at)}` : STATUS_LABELS[l.status])}
          onOpen={onOpen}
        />
      </section>

      {feed.length > 0 && (
        <section className="card p-4 lg:col-span-3">
          <h2 className="flex items-center gap-2 text-sm font-bold">
            <MessageCircle className="size-4 text-brand" /> Recent activity
          </h2>
          <ul className="mt-3 grid gap-x-6 gap-y-2 sm:grid-cols-2">
            {feed.slice(0, 12).map((item) => (
              <li key={item.id} className="min-w-0 text-sm">
                <button onClick={() => onOpen(item.lead_id)} className="font-semibold hover:text-brand">
                  {item.lead_name || 'Lead'}
                </button>{' '}
                <span className="text-fg-muted">— {item.summary}</span>
                <span className="ml-1 text-[11px] text-fg-subtle">{timeAgo(item.created_at)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function LeadList({
  leads,
  empty,
  detail,
  onOpen,
}: {
  leads: Lead[];
  empty: string;
  detail: (lead: Lead) => string;
  onOpen: (id: string) => void;
}) {
  if (!leads.length) return <p className="mt-3 text-sm text-fg-muted">{empty}</p>;
  return (
    <ul className="mt-3 space-y-1.5">
      {leads.map((lead) => (
        <li key={lead.id}>
          <button
            onClick={() => onOpen(lead.id)}
            className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-muted/60"
          >
            <span className="min-w-0 truncate font-medium">{lead.name}</span>
            <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${statusTone(lead.status)}`}>
              {detail(lead)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
