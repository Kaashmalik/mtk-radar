'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  Ban,
  Bot,
  Check,
  CheckCheck,
  Clock,
  ExternalLink,
  FileText,
  Globe2,
  Mail,
  MapPin,
  MessageCircle,
  Monitor,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings,
  Smartphone,
  X,
} from 'lucide-react';
import {
  CHANNEL_LABELS,
  LEAD_STATUSES,
  STATUS_LABELS,
  WA_SESSION_MS,
  customerActive,
  flagEmoji,
  localTime,
  placeLabel,
  statusTone,
  threadChannel,
  timeAgo,
  waWindowOpen,
  type Channel,
  type Conversation,
  type Lead,
  type LeadStatus,
  type Message,
} from '@/lib/lead-types';
import type { ChannelStatus } from '@/lib/channels';
import { WhatsappIcon } from '@/components/ui/BrandIcons';
import { inboxApi, leadsApi, type SendBody, type VisitorInfo } from '@/components/admin/client-api';
import { ErrorBanner, Toast, inputClass, usePolling, useNotice } from '@/components/admin/ui';

const DEFAULT_REPLIES = [
  'Thanks for reaching out! Could you tell me a little about your business and what you would like to build?',
  'Happy to help. Would a quick 15-minute video call work for you? I can share a booking link.',
  'Here is some of our recent work: https://mtkcodex.tech/products',
  'I will prepare a fixed quote and send it over by email today.',
];
const REPLIES_KEY = 'mtk-inbox-quick-replies-v1';
type Filter = 'all' | 'unread' | Channel;

function loadReplies(): string[] {
  try {
    const raw = window.localStorage.getItem(REPLIES_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : null;
    return Array.isArray(parsed) && parsed.every((x) => typeof x === 'string') ? parsed : DEFAULT_REPLIES;
  } catch {
    return DEFAULT_REPLIES;
  }
}

function saveReplies(replies: string[]) {
  try {
    window.localStorage.setItem(REPLIES_KEY, JSON.stringify(replies));
  } catch {
    // Private mode: quick replies just won't persist.
  }
}

function ChannelIcon({ channel, className = 'size-3.5' }: { channel: Channel; className?: string }) {
  if (channel === 'whatsapp') return <WhatsappIcon className={`${className} text-[#25d366]`} />;
  if (channel === 'email') return <Mail className={`${className} text-sky-500`} />;
  return <MessageCircle className={`${className} text-brand`} />;
}

/** Reads the deep link once: ?key=…, or the older ?wa=<digits>. */
function initialKey(): string | null {
  if (typeof window === 'undefined') return null;
  const params = new URLSearchParams(window.location.search);
  const key = params.get('key');
  if (key && threadChannel(key)) return key;
  const wa = params.get('wa');
  return wa ? `wa:${wa.replace(/\D/g, '')}` : null;
}

export default function Inbox({
  initialConversations,
  channels: initialChannels,
  defaultTemplate,
}: {
  initialConversations: Conversation[];
  channels: ChannelStatus;
  defaultTemplate: { name: string; language: string };
}) {
  const [conversations, setConversations] = useState(initialConversations);
  const [channels, setChannels] = useState(initialChannels);
  const [active, setActive] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [lead, setLead] = useState<Lead | null>(null);
  const [visitor, setVisitor] = useState<VisitorInfo | null>(null);
  const [loadingThread, setLoadingThread] = useState(false);
  const [filter, setFilter] = useState<Filter>('all');
  const [query, setQuery] = useState('');
  const [text, setText] = useState('');
  const [subject, setSubject] = useState('');
  const [template, setTemplate] = useState({ name: defaultTemplate.name, language: defaultTemplate.language, params: '' });
  const [sending, setSending] = useState(false);
  const [replies, setReplies] = useState<string[]>(DEFAULT_REPLIES);
  const [now, setNow] = useState(() => Date.now());
  const { toast, setToast, error, setError, fail } = useNotice();
  const bottomRef = useRef<HTMLDivElement>(null);
  const unreadRef = useRef(initialConversations.reduce((sum, c) => sum + c.unread, 0));
  const lastTypingPing = useRef(0);

  useEffect(() => {
    setReplies(loadReplies());
    setActive(initialKey());
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const totalUnread = conversations.reduce((sum, c) => sum + c.unread, 0);
  useEffect(() => {
    document.title = totalUnread ? `(${totalUnread}) Inbox · MTK Codex` : 'Inbox · MTK Codex';
  }, [totalUnread]);

  const refreshList = useCallback(async () => {
    try {
      const data = await inboxApi.conversations();
      setConversations(data.conversations);
      setChannels(data.channels);
      const unread = data.conversations.reduce((sum, c) => sum + c.unread, 0);
      if (
        unread > unreadRef.current &&
        document.visibilityState !== 'visible' &&
        'Notification' in window &&
        Notification.permission === 'granted'
      ) {
        const newest = [...data.conversations].sort((a, b) => b.last_at.localeCompare(a.last_at)).find((c) => c.unread > 0);
        new Notification(`New message${newest ? ` · ${newest.name}` : ''}`, { body: newest?.last_body.slice(0, 100) || 'Open the inbox', tag: newest?.key });
      }
      unreadRef.current = unread;
    } catch {
      // Transient; the next poll retries.
    }
  }, []);

  const loadThread = useCallback(
    async (key: string, quiet = false) => {
      if (!quiet) setLoadingThread(true);
      try {
        const data = await inboxApi.thread(key);
        setMessages(data.messages);
        setLead(data.lead);
        setVisitor(data.visitor);
        setConversations((list) => list.map((c) => (c.key === key ? { ...c, unread: 0 } : c)));
      } catch (err) {
        if (!quiet) fail(err);
      } finally {
        if (!quiet) setLoadingThread(false);
      }
    },
    [fail],
  );

  useEffect(() => {
    if (!active) return;
    setMessages([]);
    setLead(null);
    setVisitor(null);
    setText('');
    setSubject('');
    void loadThread(active);
  }, [active, loadThread]);

  usePolling(refreshList, 6_000);
  const pollThread = useCallback(() => {
    if (active) void loadThread(active, true);
  }, [active, loadThread]);
  // Live chat is a conversation in real time, so poll it faster.
  usePolling(pollThread, active?.startsWith('web:') ? 3_000 : 6_000, Boolean(active));

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' });
  }, [messages.length, active]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return conversations
      .filter((c) => (filter === 'all' ? true : filter === 'unread' ? c.unread > 0 : c.channel === filter))
      .filter((c) => !needle || `${c.name} ${c.subtitle} ${c.last_body} ${placeLabel(c.place)}`.toLowerCase().includes(needle))
      .sort((a, b) => Number(Boolean(b.online)) - Number(Boolean(a.online)) || b.last_at.localeCompare(a.last_at));
  }, [conversations, filter, query]);

  const channel = active ? threadChannel(active) : null;
  const conversation = conversations.find((c) => c.key === active);
  const lastInbound = [...messages].reverse().find((m) => m.direction === 'in')?.created_at || lead?.last_inbound_at || null;
  const windowOpen = waWindowOpen(lastInbound, now);
  const windowLeft = lastInbound ? WA_SESSION_MS - (now - new Date(lastInbound).getTime()) : 0;
  const blocked = Boolean(lead?.do_not_contact);
  const place = visitor
    ? { city: visitor.city, region: visitor.region, country: visitor.country, timezone: visitor.timezone }
    : lead
      ? { city: lead.city || '', region: lead.region || '', country: lead.country || '', timezone: lead.timezone || '' }
      : null;
  const theirTime = localTime(place?.timezone, new Date(now));
  const lastSubject = [...messages].reverse().find((m) => m.subject)?.subject || '';

  async function send(body: SendBody) {
    if (!active) return;
    setSending(true);
    setError('');
    try {
      const message = await inboxApi.send(active, body);
      setMessages((list) => [...list, message]);
      setText('');
      setSubject('');
      setToast(body.template ? 'Template sent' : message.meta?.emailed ? 'Sent — also emailed (visitor left)' : 'Sent');
      void refreshList();
    } catch (err) {
      fail(err);
    } finally {
      setSending(false);
    }
  }

  function onType(value: string) {
    setText(value);
    // Throttled "typing…" signal for the visitor's widget.
    if (active?.startsWith('web:') && Date.now() - lastTypingPing.current > 3_000) {
      lastTypingPing.current = Date.now();
      void inboxApi.typing(active).catch(() => undefined);
    }
  }

  async function changeStatus(status: LeadStatus) {
    if (!lead) return;
    try {
      setLead(await leadsApi.patch(lead.id, { status }));
      setToast(`Status → ${STATUS_LABELS[status]}`);
    } catch (err) {
      fail(err);
    }
  }

  const title = lead?.name || visitor?.name || conversation?.name || active?.slice(active.indexOf(':') + 1) || '';
  const counts = {
    web: conversations.filter((c) => c.channel === 'web').length,
    whatsapp: conversations.filter((c) => c.channel === 'whatsapp').length,
    email: conversations.filter((c) => c.channel === 'email').length,
  };
  const onlineNow = conversations.filter((c) => c.online).length;

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow">Inbox</p>
          <h1 className="mt-2 text-3xl font-bold">Conversations</h1>
          <p className="mt-1 text-sm text-fg-muted">
            Live chat, WhatsApp and email in one place.{' '}
            {onlineNow > 0 && <span className="font-semibold text-emerald-600">{onlineNow} visitor{onlineNow > 1 ? 's' : ''} chatting now.</span>}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
          {(
            [
              ['Live chat', channels.chat],
              ['WhatsApp', channels.whatsapp],
              ['Email in', channels.emailReceive],
              ['Email out', channels.emailSend],
              ['Phone alerts', channels.push || channels.telegram],
            ] as [string, boolean][]
          ).map(([label, on]) => (
            <span
              key={label}
              className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 font-semibold ${
                on ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' : 'border-line text-fg-subtle'
              }`}
            >
              <span className={`size-1.5 rounded-full ${on ? 'bg-emerald-500' : 'bg-fg-subtle/50'}`} /> {label}
            </span>
          ))}
          <Link
            href="/admin/settings"
            className="inline-flex h-7 items-center gap-1 rounded-full border border-line px-2.5 font-semibold text-fg-muted hover:border-brand hover:text-brand"
          >
            <Settings className="size-3" /> Set up
          </Link>
        </div>
      </div>

      <ErrorBanner message={error} onDismiss={() => setError('')} />

      <div className="mt-4 grid h-[calc(100dvh-14rem)] min-h-[540px] overflow-hidden rounded-2xl border border-line bg-elevated md:grid-cols-[330px_1fr]">
        <aside className={`flex min-h-0 flex-col border-r border-line ${active ? 'hidden md:flex' : 'flex'}`}>
          <div className="space-y-2 border-b border-line p-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-fg-subtle" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search name, city, message…"
                aria-label="Search conversations"
                className="h-9 w-full rounded-full border border-line bg-bg pl-9 pr-3 text-sm outline-none focus:border-brand"
              />
            </div>
            <div className="flex flex-wrap gap-1 text-xs">
              {(
                [
                  ['all', `All ${conversations.length}`],
                  ['unread', `Unread ${totalUnread}`],
                  ['web', `Chat ${counts.web}`],
                  ['whatsapp', `WhatsApp ${counts.whatsapp}`],
                  ['email', `Email ${counts.email}`],
                ] as [Filter, string][]
              ).map(([value, label]) => (
                <button
                  key={value}
                  onClick={() => setFilter(value)}
                  className={`rounded-full px-2.5 py-1 font-semibold ${filter === value ? 'bg-brand-soft text-brand' : 'text-fg-muted hover:text-fg'}`}
                >
                  {label}
                </button>
              ))}
              <button onClick={refreshList} className="ml-auto text-fg-subtle hover:text-brand" aria-label="Refresh">
                <RefreshCw className="size-3.5" />
              </button>
            </div>
          </div>
          <ul className="min-h-0 flex-1 overflow-y-auto">
            {visible.map((c) => (
              <li key={c.key}>
                <button
                  onClick={() => setActive(c.key)}
                  className={`flex w-full gap-3 border-b border-line/60 px-3 py-3 text-left transition hover:bg-muted/50 ${active === c.key ? 'bg-brand-soft/50' : ''}`}
                >
                  <span className="relative grid size-10 shrink-0 place-items-center rounded-full bg-muted text-sm font-bold text-fg-muted">
                    {c.place?.country ? <span className="text-lg">{flagEmoji(c.place.country)}</span> : c.name.replace(/[^A-Za-z0-9]/g, '').slice(0, 2).toUpperCase() || '#'}
                    <span className="absolute -bottom-0.5 -right-0.5 grid size-5 place-items-center rounded-full border border-line bg-elevated">
                      <ChannelIcon channel={c.channel} className="size-3" />
                    </span>
                    {(c.online || customerActive(c.last_inbound_at, now)) && (
                      <span className="absolute -left-0.5 -top-0.5 size-3 rounded-full border-2 border-elevated bg-emerald-500" title="Active now" />
                    )}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center justify-between gap-2">
                      <span className={`truncate text-sm ${c.unread ? 'font-bold' : 'font-semibold'}`}>{c.name}</span>
                      <span className="shrink-0 text-[10px] text-fg-subtle">{timeAgo(c.last_at, now)}</span>
                    </span>
                    {c.place?.city && <span className="block truncate text-[11px] text-fg-subtle">{placeLabel(c.place)}</span>}
                    <span className="flex items-center justify-between gap-2">
                      <span className={`truncate text-xs ${c.unread ? 'text-fg' : 'text-fg-subtle'}`}>
                        {c.last_direction === 'out' && 'You: '}
                        {c.last_body}
                      </span>
                      {c.unread > 0 && <span className="shrink-0 rounded-full bg-cta px-1.5 text-[10px] font-bold text-on-cta">{c.unread}</span>}
                      {c.do_not_contact && <Ban className="size-3 shrink-0 text-red-500" aria-label="Opted out" />}
                    </span>
                  </span>
                </button>
              </li>
            ))}
            {!visible.length && (
              <li className="p-6 text-center text-sm text-fg-muted">
                {conversations.length ? 'No conversations match.' : 'No conversations yet. Website chats, WhatsApp replies and emails will appear here.'}
              </li>
            )}
          </ul>
        </aside>

        <section className={`min-h-0 flex-col ${active ? 'flex' : 'hidden md:flex'}`}>
          {!active || !channel ? (
            <div className="grid flex-1 place-items-center p-8 text-center text-sm text-fg-muted">
              <div>
                <MessageCircle className="mx-auto size-10 text-fg-subtle" />
                <p className="mt-2">Pick a conversation to read and reply.</p>
              </div>
            </div>
          ) : (
            <>
              <header className="border-b border-line px-4 py-3">
                <div className="flex flex-wrap items-center gap-3">
                  <button onClick={() => setActive(null)} className="md:hidden" aria-label="Back to conversations">
                    <ArrowLeft className="size-5" />
                  </button>
                  <div className="min-w-0 flex-1">
                    <p className="flex items-center gap-2 truncate font-bold">
                      <ChannelIcon channel={channel} /> {title}
                      <span className="rounded-full border border-line px-2 py-0.5 text-[10px] font-semibold text-fg-subtle">{CHANNEL_LABELS[channel]}</span>
                    </p>
                    <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-fg-subtle">
                      {channel === 'web' && visitor && (
                        visitor.online ? (
                          <span className="inline-flex items-center gap-1 font-semibold text-emerald-600">
                            <span className="size-1.5 rounded-full bg-emerald-500" /> Online now{visitor.page ? ` · on ${visitor.page}` : ''}
                          </span>
                        ) : (
                          <span>Left {timeAgo(visitor.last_seen_at, now)}</span>
                        )
                      )}
                      {place && placeLabel(place) && (
                        <span className="inline-flex items-center gap-1">
                          <MapPin className="size-3" /> {flagEmoji(place.country)} {placeLabel(place)}
                        </span>
                      )}
                      {theirTime && (
                        <span className="inline-flex items-center gap-1">
                          <Clock className="size-3" /> Their time {theirTime}
                        </span>
                      )}
                      {channel === 'web' && visitor?.device && (
                        <span className="inline-flex items-center gap-1">
                          {visitor.device === 'desktop' ? <Monitor className="size-3" /> : <Smartphone className="size-3" />} {visitor.device}
                        </span>
                      )}
                      {channel === 'whatsapp' &&
                        (windowOpen ? (
                          <span className="inline-flex items-center gap-1 text-emerald-600">
                            <Clock className="size-3" /> Reply window {Math.max(1, Math.floor(windowLeft / 3_600_000))}h left
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-amber-600">
                            <Clock className="size-3" /> Window closed — template only
                          </span>
                        ))}
                      {channel === 'email' && <span className="font-mono">{active.slice(6)}</span>}
                      {channel === 'web' && visitor && (visitor.email || visitor.phone) && (
                        <span className="font-mono">{[visitor.email, visitor.phone].filter(Boolean).join(' · ')}</span>
                      )}
                    </p>
                  </div>
                  {lead && (
                    <>
                      <select
                        aria-label="Lead status"
                        value={lead.status}
                        onChange={(e) => changeStatus(e.target.value as LeadStatus)}
                        className={`h-8 rounded-full border px-2.5 text-[11px] font-semibold ${statusTone(lead.status)}`}
                      >
                        {LEAD_STATUSES.map((value) => (
                          <option key={value} value={value} disabled={value === 'queued' && lead.do_not_contact} className="bg-elevated text-fg">
                            {STATUS_LABELS[value]}
                          </option>
                        ))}
                      </select>
                      <a
                        href={`/admin?lead=${encodeURIComponent(lead.id)}`}
                        className="inline-flex h-8 items-center gap-1 rounded-full border border-line px-3 text-xs font-semibold text-fg-muted hover:border-brand hover:text-brand"
                      >
                        <ExternalLink className="size-3" /> Lead
                      </a>
                      {lead.email && channel !== 'email' && (
                        <button
                          onClick={() => setActive(`email:${lead.email.toLowerCase()}`)}
                          className="inline-flex h-8 items-center gap-1 rounded-full border border-line px-3 text-xs font-semibold text-fg-muted hover:border-brand hover:text-brand"
                        >
                          <Mail className="size-3" /> Email
                        </button>
                      )}
                    </>
                  )}
                </div>
              </header>

              <div className="min-h-0 flex-1 space-y-2 overflow-y-auto bg-muted/30 px-4 py-4">
                {loadingThread && <p className="text-center text-xs text-fg-subtle">Loading…</p>}
                {!loadingThread && !messages.length && (
                  <p className="mx-auto max-w-sm text-center text-xs text-fg-subtle">
                    {channel === 'email' ? 'No emails yet. Write the first one below.' : channel === 'whatsapp' ? 'No messages yet. Start with an approved template.' : 'No messages yet.'}
                  </p>
                )}
                {messages.map((m, index) => {
                  const showDay = index === 0 || new Date(messages[index - 1].created_at).toDateString() !== new Date(m.created_at).toDateString();
                  const mine = m.direction === 'out';
                  const bot = m.sender === 'bot';
                  return (
                    <div key={m.id}>
                      {showDay && (
                        <p className="my-3 text-center text-[10px] font-semibold uppercase tracking-wide text-fg-subtle">
                          {new Date(m.created_at).toLocaleDateString('en-PK', { weekday: 'short', day: 'numeric', month: 'short' })}
                        </p>
                      )}
                      <div className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
                        <div
                          className={`max-w-[82%] whitespace-pre-wrap break-words rounded-2xl px-3 py-2 text-sm shadow-sm ${
                            bot
                              ? 'rounded-br-sm border border-dashed border-line bg-elevated text-fg-muted'
                              : mine
                                ? 'rounded-br-sm bg-[#d9fdd3] text-[#0b2a18] dark:bg-[#11503a] dark:text-white'
                                : 'rounded-bl-sm bg-elevated'
                          }`}
                        >
                          {bot && (
                            <span className="mb-1 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide">
                              <Bot className="size-3" /> Auto-reply
                            </span>
                          )}
                          {m.subject && <span className="mb-1 block text-xs font-bold">{m.subject}</span>}
                          {m.body}
                          <span className="mt-1 flex items-center justify-end gap-1 text-[10px] opacity-60">
                            {m.meta?.emailed === true && 'emailed · '}
                            {new Date(m.created_at).toLocaleTimeString('en-PK', { hour: 'numeric', minute: '2-digit' })}
                            {mine && !bot && <DeliveryTick status={m.status} />}
                          </span>
                          {m.status === 'failed' && <span className="block text-[10px] text-red-500">Failed: {m.error || 'not delivered'}</span>}
                        </div>
                      </div>
                    </div>
                  );
                })}
                {channel === 'web' && visitor?.typing && (
                  <p className="text-xs italic text-fg-subtle">{visitor.name || 'Visitor'} is typing…</p>
                )}
                <div ref={bottomRef} />
              </div>

              <footer className="border-t border-line p-3">
                {blocked ? (
                  <p className="flex items-center gap-2 rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-500">
                    <Ban className="size-4" /> This contact opted out. Messaging is blocked.
                  </p>
                ) : channel === 'whatsapp' && !channels.whatsapp ? (
                  <SetupHint text="Connect the WhatsApp Cloud API to reply from here." />
                ) : channel === 'email' && !channels.emailSend ? (
                  <SetupHint text="Verify your domain in Resend and set EMAIL_FROM to send email from here." />
                ) : channel === 'whatsapp' && !windowOpen ? (
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      const params = template.params.split('|').map((p) => p.trim()).filter(Boolean);
                      void send({ template: { name: template.name, language: template.language, params } });
                    }}
                    className="space-y-2"
                  >
                    <p className="flex items-start gap-1.5 text-[11px] text-fg-subtle">
                      <FileText className="mt-0.5 size-3 shrink-0" />
                      WhatsApp only allows a pre-approved template until the customer writes back. Their reply reopens free text for 24h.
                    </p>
                    <div className="grid gap-2 sm:grid-cols-[1fr_90px_1fr_auto]">
                      <input value={template.name} onChange={(e) => setTemplate({ ...template, name: e.target.value })} placeholder="template_name" aria-label="Template name" className={inputClass} required />
                      <input value={template.language} onChange={(e) => setTemplate({ ...template, language: e.target.value })} placeholder="en" aria-label="Template language" className={inputClass} required />
                      <input value={template.params} onChange={(e) => setTemplate({ ...template, params: e.target.value })} placeholder="Variables, split with |" aria-label="Template variables" className={inputClass} />
                      <button type="submit" disabled={sending || !template.name.trim()} className="inline-flex h-10 items-center justify-center gap-1.5 rounded-full bg-[#25d366] px-4 text-sm font-semibold text-white disabled:opacity-50">
                        {sending ? <RefreshCw className="size-4 animate-spin" /> : <Send className="size-4" />} Send template
                      </button>
                    </div>
                  </form>
                ) : (
                  <>
                    {channel === 'web' && visitor && !visitor.online && (
                      <p className="mb-2 text-[11px] text-amber-600">
                        {visitor.email
                          ? `The visitor left — your reply will also be emailed to ${visitor.email}${channels.emailSend ? '' : ' (once email sending is set up)'}.`
                          : 'The visitor left without an email. They will see your reply if they come back to the site.'}
                      </p>
                    )}
                    <QuickReplies replies={replies} current={text} onPick={setText} onChange={(next) => {
                      setReplies(next);
                      saveReplies(next);
                    }} />
                    {channel === 'email' && (
                      <input
                        value={subject}
                        onChange={(e) => setSubject(e.target.value)}
                        placeholder={lastSubject ? (/^re:/i.test(lastSubject) ? lastSubject : `Re: ${lastSubject}`) : 'Subject'}
                        aria-label="Email subject"
                        className={`${inputClass} mb-2`}
                      />
                    )}
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        if (text.trim()) void send({ text, subject: subject || undefined });
                      }}
                      className="flex items-end gap-2"
                    >
                      <textarea
                        value={text}
                        onChange={(e) => onType(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && !e.shiftKey && channel !== 'email') {
                            e.preventDefault();
                            if (text.trim()) void send({ text });
                          }
                        }}
                        rows={channel === 'email' ? 5 : 2}
                        placeholder={channel === 'email' ? 'Write your email…' : 'Type a reply… (Enter to send, Shift+Enter for a new line)'}
                        aria-label="Reply"
                        className="min-h-11 flex-1 resize-y rounded-2xl border border-line bg-bg px-3 py-2 text-sm outline-none focus:border-brand"
                      />
                      <button
                        type="submit"
                        disabled={sending || !text.trim()}
                        className={`grid size-11 shrink-0 place-items-center rounded-full text-white transition hover:brightness-105 disabled:opacity-50 ${
                          channel === 'whatsapp' ? 'bg-[#25d366]' : channel === 'email' ? 'bg-sky-600' : 'bg-cta text-on-cta'
                        }`}
                        aria-label="Send"
                      >
                        {sending ? <RefreshCw className="size-4 animate-spin" /> : <Send className="size-4" />}
                      </button>
                    </form>
                  </>
                )}
              </footer>
            </>
          )}
        </section>
      </div>
      <p className="mt-3 flex items-center gap-1.5 text-[11px] text-fg-subtle">
        <Globe2 className="size-3" /> Locations are city-level, from your host&apos;s edge network. Keep this tab open (or install the app) so visitors see you as online.
      </p>
      <Toast message={toast} />
    </div>
  );
}

function SetupHint({ text }: { text: string }) {
  return (
    <p className="flex items-center justify-between gap-2 rounded-xl bg-muted/60 px-3 py-2 text-xs text-fg-muted">
      {text}
      <Link href="/admin/settings" className="shrink-0 font-semibold text-brand">
        Set up →
      </Link>
    </p>
  );
}

function DeliveryTick({ status }: { status: Message['status'] }) {
  if (status === 'read') return <CheckCheck className="size-3 text-sky-500" aria-label="Read" />;
  if (status === 'delivered') return <CheckCheck className="size-3" aria-label="Delivered" />;
  if (status === 'failed') return <X className="size-3 text-red-500" aria-label="Failed" />;
  return <Check className="size-3" aria-label="Sent" />;
}

function QuickReplies({
  replies,
  current,
  onPick,
  onChange,
}: {
  replies: string[];
  current: string;
  onPick: (text: string) => void;
  onChange: (replies: string[]) => void;
}) {
  return (
    <div className="mb-2 flex gap-1.5 overflow-x-auto pb-1">
      {replies.map((reply, index) => (
        <span key={index} className="group inline-flex shrink-0 items-center rounded-full border border-line bg-bg text-[11px]">
          <button type="button" onClick={() => onPick(reply)} className="max-w-[220px] truncate px-2.5 py-1 text-fg-muted hover:text-brand" title={reply}>
            {reply}
          </button>
          <button
            type="button"
            onClick={() => onChange(replies.filter((_, i) => i !== index))}
            className="pr-2 text-fg-subtle opacity-0 hover:text-red-500 group-hover:opacity-100"
            aria-label="Remove quick reply"
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
      {current.trim() && !replies.includes(current.trim()) && (
        <button
          type="button"
          onClick={() => onChange([...replies, current.trim()])}
          className="inline-flex shrink-0 items-center gap-1 rounded-full border border-dashed border-line px-2.5 py-1 text-[11px] font-semibold text-brand"
        >
          <Plus className="size-3" /> Save as quick reply
        </button>
      )}
    </div>
  );
}
