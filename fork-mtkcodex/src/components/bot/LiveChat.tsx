'use client';

import { useEffect, useRef, useState } from 'react';
import { CalendarClock, Loader2, Mail, MessageCircle, Phone, Send, ShieldCheck } from 'lucide-react';
import { WhatsappIcon } from '@/components/ui/BrandIcons';
import { formatInZone, nextOpening, officeOpen } from '@/lib/business-hours';
import { whatsappLink } from '@/data/site';
import type { Agent, ChatMessage } from './useLiveChat';

const BOOKING_URL = process.env.NEXT_PUBLIC_BOOKING_URL || '';

const browserZone = () => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return undefined;
  }
};

type Props = {
  agent: Agent;
  messages: ChatMessage[];
  identified: boolean;
  error: string;
  onSend: (text: string) => Promise<void>;
  onIdentify: (details: { name: string; email: string; phone: string; preferred_channel: string; website?: string }) => Promise<void>;
  onTyping: () => void;
};

/** The "Chat with the team" tab inside the site widget. */
export default function LiveChat({ agent, messages, identified, error, onSend, onIdentify, onTyping }: Props) {
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [askDetails, setAskDetails] = useState(false);
  const [skipped, setSkipped] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [backAt, setBackAt] = useState('');

  useEffect(() => {
    // Computed after mount: it depends on the visitor's own clock and timezone.
    setBackAt(officeOpen() ? '' : formatInZone(nextOpening(), browserZone()));
    setTimeout(() => inputRef.current?.focus(), 100);
  }, []);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages.length, agent.typing, askDetails]);

  const sentSomething = messages.some((m) => m.direction === 'in');
  useEffect(() => {
    if (sentSomething && !identified && !skipped) setAskDetails(true);
  }, [sentSomething, identified, skipped]);

  async function submit(event?: React.FormEvent) {
    event?.preventDefault();
    const text = input.trim();
    if (!text || sending) return;
    setSending(true);
    setInput('');
    try {
      await onSend(text);
    } catch {
      setInput(text);
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <div className="flex items-center gap-2 border-b border-line bg-elevated px-4 py-2 text-xs">
        <span className={`size-2 rounded-full ${agent.online ? 'bg-emerald-500' : 'bg-amber-400'}`} />
        {agent.online ? (
          <span>
            <strong>{agent.name}</strong> is online · usually replies in a few minutes
          </span>
        ) : (
          <span>
            We&apos;re away{backAt ? ` · back ${backAt} your time` : ''} · we reply by email too
          </span>
        )}
      </div>

      <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto bg-bg p-4" aria-live="polite">
        {!messages.length && (
          <div className="rounded-2xl border border-line bg-elevated p-4 text-sm leading-relaxed">
            <p className="font-semibold">Talk to the MTK Codex team 👋</p>
            <p className="mt-1 text-fg-muted">
              Ask anything about your project — we work with clients in Pakistan, the UK, the US and the Gulf. Messages go
              straight to {agent.name}.
            </p>
            {BOOKING_URL && (
              <a
                href={BOOKING_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1.5 text-xs font-semibold text-brand hover:border-brand"
              >
                <CalendarClock className="size-3.5" /> Book a free 15-min video call
              </a>
            )}
          </div>
        )}
        {messages.map((m) =>
          m.direction === 'in' ? (
            <div key={m.id} className="flex justify-end">
              <div className={`max-w-[82%] whitespace-pre-wrap break-words rounded-2xl rounded-br-sm bg-cta px-3.5 py-2.5 text-sm text-on-cta ${m.pending ? 'opacity-60' : ''}`}>
                {m.body}
              </div>
            </div>
          ) : (
            <div key={m.id} className="flex items-end gap-2">
              <span className="grid size-7 shrink-0 place-items-center rounded-full bg-brand-soft text-[11px] font-bold text-brand">
                {m.sender === 'bot' ? <MessageCircle className="size-3.5" /> : agent.name.slice(0, 1)}
              </span>
              <div className="max-w-[82%] whitespace-pre-wrap break-words rounded-2xl rounded-bl-sm border border-line bg-elevated px-3.5 py-2.5 text-sm leading-relaxed">
                <span className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wide text-fg-subtle">
                  {m.sender === 'bot' ? 'Automatic reply' : agent.name}
                </span>
                {m.body}
              </div>
            </div>
          ),
        )}
        {agent.typing && <p className="text-xs italic text-fg-subtle">{agent.name} is typing…</p>}
        {askDetails && !identified && (
          <DetailsCard
            onSubmit={async (details) => {
              await onIdentify(details);
              setAskDetails(false);
            }}
            onSkip={() => {
              setSkipped(true);
              setAskDetails(false);
            }}
          />
        )}
      </div>

      <div className="border-t border-line bg-elevated p-3">
        {error && <p className="mb-2 text-xs text-red-500">{error}</p>}
        <form onSubmit={submit} className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => {
              setInput(e.target.value);
              onTyping();
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void submit();
              }
            }}
            rows={1}
            maxLength={2000}
            placeholder="Write your message…"
            aria-label="Your message"
            className="max-h-28 min-h-11 min-w-0 flex-1 resize-none rounded-2xl border border-line bg-bg px-4 py-2.5 text-sm outline-none transition focus:border-brand"
          />
          <button
            type="submit"
            aria-label="Send"
            disabled={!input.trim() || sending}
            className="grid size-11 shrink-0 place-items-center rounded-full bg-cta text-on-cta transition hover:bg-cta-hover disabled:opacity-50"
          >
            {sending ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
          </button>
        </form>
        <div className="mt-2 flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-[11px] text-fg-subtle">
          <a href={whatsappLink()} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 hover:text-brand">
            <WhatsappIcon className="size-3 text-[#25d366]" /> WhatsApp
          </a>
          <a href="/contact" className="inline-flex items-center gap-1 hover:text-brand">
            <Mail className="size-3" /> Email form
          </a>
          {BOOKING_URL && (
            <a href={BOOKING_URL} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 hover:text-brand">
              <CalendarClock className="size-3" /> Book a call
            </a>
          )}
        </div>
      </div>
    </>
  );
}

const CHANNELS: [string, string, React.ComponentType<{ className?: string }>][] = [
  ['email', 'Email', Mail],
  ['whatsapp', 'WhatsApp', MessageCircle],
  ['call', 'Video call', Phone],
];

function DetailsCard({
  onSubmit,
  onSkip,
}: {
  onSubmit: (details: { name: string; email: string; phone: string; preferred_channel: string; website?: string }) => Promise<void>;
  onSkip: () => void;
}) {
  const [form, setForm] = useState({ name: '', email: '', phone: '', preferred_channel: 'email', website: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const field = 'h-9 w-full rounded-xl border border-line bg-bg px-3 text-sm outline-none focus:border-brand';

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError('');
        try {
          await onSubmit(form);
        } catch (err) {
          setError(err instanceof Error ? err.message : 'Could not save');
          setBusy(false);
        }
      }}
      className="rounded-2xl border border-brand/30 bg-elevated p-3 text-sm"
    >
      <p className="font-semibold">So we can reply if you leave</p>
      <p className="mt-0.5 text-xs text-fg-subtle">We only use this to answer you. No newsletters.</p>
      <div className="mt-2 space-y-2">
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Your name" autoComplete="name" aria-label="Your name" className={field} />
        <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="Email" autoComplete="email" aria-label="Email" className={field} />
        <input type="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="Phone with country code, e.g. +44 7…" autoComplete="tel" aria-label="Phone" className={field} />
        <input tabIndex={-1} autoComplete="off" aria-hidden className="hidden" value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} />
        <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Best way to reach you">
          {CHANNELS.map(([value, label, Icon]) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={form.preferred_channel === value}
              onClick={() => setForm({ ...form, preferred_channel: value })}
              className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold ${
                form.preferred_channel === value ? 'border-brand bg-brand-soft text-brand' : 'border-line text-fg-muted'
              }`}
            >
              <Icon className="size-3" /> {label}
            </button>
          ))}
        </div>
      </div>
      {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
      <div className="mt-3 flex items-center justify-between gap-2">
        <button type="button" onClick={onSkip} className="text-xs text-fg-subtle hover:text-fg">
          Not now
        </button>
        <button
          type="submit"
          disabled={busy || (!form.email.trim() && !form.phone.trim())}
          className="inline-flex h-9 items-center gap-1.5 rounded-full bg-cta px-4 text-xs font-semibold text-on-cta disabled:opacity-50"
        >
          {busy ? <Loader2 className="size-3.5 animate-spin" /> : <ShieldCheck className="size-3.5" />} Save
        </button>
      </div>
    </form>
  );
}
