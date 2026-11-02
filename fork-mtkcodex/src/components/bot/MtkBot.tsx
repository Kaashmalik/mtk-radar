'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Fragment, useEffect, useRef, useState } from 'react';
import { ArrowRight, ArrowUpRight, Bot, LayoutGrid, MessageCircle, RotateCcw, Send, X } from 'lucide-react';
import { MENU, answer, contextReply, welcome, type BotReply } from '@/data/bot';
import { whatsappLink } from '@/data/site';
import { WhatsappIcon } from '@/components/ui/BrandIcons';
import BotMascot from './BotMascot';
import LiveChat from './LiveChat';
import { useLiveChat } from './useLiveChat';

type Msg = { from: 'bot' | 'user'; reply: BotReply };

const STORE = 'mtk-bot-chat-v2';
const HUMAN = /^(talk to a human|human|agent|real person|live chat|chat with (the )?team)$/i;

/** Renders **bold** segments without injecting HTML. */
function RichText({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
        part.startsWith('**') ? (
          <strong key={i} className="font-semibold">
            {part.slice(2, -2)}
          </strong>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}

function BotLinkChip({ href, label }: { href: string; label: string }) {
  const external = /^(https?:|mailto:)/.test(href);
  const cls = 'inline-flex items-center gap-1 rounded-full border border-line bg-elevated px-3 py-1 text-xs font-semibold text-brand transition hover:border-brand';
  const isWa = href.includes('wa.me');
  const inner = (
    <>
      {isWa && <WhatsappIcon className="size-3.5 text-[#25d366]" />}
      {label}
      {external ? !isWa && <ArrowUpRight className="size-3" /> : <ArrowRight className="size-3" />}
    </>
  );
  return external ? (
    <a href={href} target="_blank" rel="noopener noreferrer" className={cls}>
      {inner}
    </a>
  ) : (
    <Link href={href} className={cls}>
      {inner}
    </Link>
  );
}

export default function MtkBot() {
  const [open, setOpen] = useState(false);
  const [hover, setHover] = useState(false);
  const [teaser, setTeaser] = useState(false);
  const [teaserClosed, setTeaserClosed] = useState(false);
  const [typing, setTyping] = useState(false);
  const [input, setInput] = useState('');
  const [msgs, setMsgs] = useState<Msg[]>([{ from: 'bot', reply: welcome }]);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const pathname = usePathname();
  const greeted = useRef(new Set<string>());
  const [mode, setMode] = useState<'bot' | 'live'>('bot');
  const live = useLiveChat({ active: open && mode === 'live', pathname });
  const liveAvailable = live.enabled === true;

  // Restore this tab's conversation.
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem(STORE);
      if (saved) setMsgs(JSON.parse(saved));
      if (localStorage.getItem('mtk-bot-teaser-closed') === '1') setTeaserClosed(true);
    } catch {}
    // Any link to #mtk-bot opens the chat.
    const fromHash = () => {
      if (location.hash === '#mtk-bot') setOpen(true);
      if (location.hash === '#live-chat') {
        setMode('live');
        setOpen(true);
      }
    };
    fromHash();
    window.addEventListener('hashchange', fromHash);
    // A "continue the chat" link from an email opens straight into the live chat.
    const openLive = () => {
      setMode('live');
      setOpen(true);
    };
    window.addEventListener('mtk-chat-open', openLive);
    const t = setTimeout(() => setTeaser(true), 4000);
    return () => {
      clearTimeout(t);
      window.removeEventListener('hashchange', fromHash);
      window.removeEventListener('mtk-chat-open', openLive);
    };
  }, []);

  useEffect(() => {
    try {
      sessionStorage.setItem(STORE, JSON.stringify(msgs.slice(-30)));
    } catch {}
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [msgs, typing]);

  useEffect(() => {
    if (open) {
      setTeaser(false);
      setTimeout(() => inputRef.current?.focus(), 150);
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  useEffect(() => {
    if (!open || greeted.current.has(pathname)) return;
    greeted.current.add(pathname);
    const ctx = contextReply(pathname);
    if (ctx) setMsgs((m) => (m[m.length - 1]?.reply.text === ctx.text ? m : [...m, { from: 'bot', reply: ctx }]));
  }, [open, pathname]);

  const ask = (q: string) => {
    const question = q.trim().slice(0, 300);
    if (!question || typing) return;
    // People asking for a person get one, when live chat is available.
    if (liveAvailable && HUMAN.test(question)) {
      setInput('');
      setMode('live');
      return;
    }
    setMsgs((m) => [...m, { from: 'user', reply: { text: question } }]);
    setInput('');
    setTyping(true);
    // Short "thinking" delay makes the conversation feel natural.
    setTimeout(() => {
      setMsgs((m) => [...m, { from: 'bot', reply: answer(question) }]);
      setTyping(false);
    }, 650 + Math.min(900, question.length * 12));
  };

  const reset = () => {
    greeted.current.clear();
    setMsgs([{ from: 'bot', reply: welcome }]);
  };

  const closeTeaser = () => {
    setTeaser(false);
    setTeaserClosed(true);
    try {
      localStorage.setItem('mtk-bot-teaser-closed', '1');
    } catch {}
  };

  // Chips follow the latest bot answer; Menu is always reachable.
  const lastBot = [...msgs].reverse().find((m) => m.from === 'bot');
  const suggestions = (lastBot?.reply.suggestions ?? MENU).filter((x) => x !== 'Menu');

  return (
    <>
      {/* Launcher */}
      <div className="fixed bottom-[88px] right-4 z-[65] flex items-end gap-2 sm:right-5">
        {teaser && !open && !teaserClosed && (
          <div className="word-in relative mb-6 hidden sm:block">
            <button
              type="button"
              onClick={() => setOpen(true)}
              className="block max-w-[210px] rounded-2xl rounded-br-sm border border-line bg-elevated px-4 py-2.5 text-left text-sm shadow-float"
            >
              <span className="font-semibold">Hi! I&apos;m MTK Bot 👋</span>
              <span className="block text-xs text-fg-muted">Questions about our products? Ask me!</span>
            </button>
            <button
              type="button"
              onClick={closeTeaser}
              aria-label="Dismiss MTK Bot teaser"
              className="absolute -right-1.5 -top-1.5 grid size-6 place-items-center rounded-full border border-line bg-elevated text-fg-muted shadow-float transition hover:text-brand"
            >
              <X className="size-3.5" />
            </button>
          </div>
        )}
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          onMouseEnter={() => setHover(true)}
          onMouseLeave={() => setHover(false)}
          aria-label={open ? 'Close chat' : 'Open chat with MTK Codex'}
          aria-expanded={open}
          className="relative grid size-16 place-items-center rounded-full transition hover:scale-105"
        >
          {open ? (
            <span className="grid size-14 place-items-center rounded-full bg-cta text-on-cta shadow-float">
              <X className="size-6" />
            </span>
          ) : (
            <>
              <span className="absolute inset-1 rounded-full bg-cta/25 blur-md" />
              <BotMascot size={64} waving={hover || teaser} />
            </>
          )}
          {!open && live.unread > 0 && (
            <span className="absolute right-0 top-0 grid min-w-5 place-items-center rounded-full bg-red-500 px-1 text-[11px] font-bold text-white shadow" aria-label={`${live.unread} new replies`}>
              {live.unread}
            </span>
          )}
        </button>
      </div>

      {/* Chat panel */}
      {open && (
        <div
          role="dialog"
          aria-label="MTK Bot chat"
          className="word-in fixed inset-x-2 bottom-2 z-[75] flex max-h-[min(640px,calc(100dvh-16px))] flex-col overflow-hidden rounded-3xl border border-line bg-elevated shadow-float sm:inset-x-auto sm:bottom-[170px] sm:right-5 sm:w-[380px] sm:max-h-[min(600px,calc(100dvh-190px))]"
        >
          <div className="night flex items-center gap-3 px-4 py-3">
            <span className="grid size-12 place-items-center rounded-2xl bg-white/10">
              <BotMascot size={44} follow={false} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-display font-bold">{mode === 'live' ? `Chat with ${live.agent.name}` : 'MTK Bot'}</p>
              <p className="flex items-center gap-1.5 text-xs text-white/70">
                <span className={`pulse-dot size-1.5 rounded-full ${mode === 'live' && !live.agent.online ? 'bg-amber-300 text-amber-300' : 'bg-lime text-lime'}`} />
                {mode === 'live' ? (live.agent.online ? 'Online now' : 'Away · replies by email') : 'Online · instant answers'}
              </p>
            </div>
            {mode === 'bot' && (
              <button type="button" onClick={reset} aria-label="Restart conversation" className="grid size-8 place-items-center rounded-full text-white/70 hover:bg-white/10 hover:text-white">
                <RotateCcw className="size-4" />
              </button>
            )}
            <button type="button" onClick={() => setOpen(false)} aria-label="Close chat" className="grid size-8 place-items-center rounded-full text-white/70 hover:bg-white/10 hover:text-white">
              <X className="size-5" />
            </button>
          </div>

          {liveAvailable && (
            <div className="grid grid-cols-2 gap-1 border-b border-line bg-elevated p-1.5" role="tablist" aria-label="Chat mode">
              {(
                [
                  ['bot', 'Instant answers', Bot],
                  ['live', 'Chat with the team', MessageCircle],
                ] as const
              ).map(([value, label, Icon]) => (
                <button
                  key={value}
                  type="button"
                  role="tab"
                  aria-selected={mode === value}
                  onClick={() => setMode(value)}
                  className={`relative inline-flex items-center justify-center gap-1.5 rounded-xl py-2 text-xs font-semibold transition ${
                    mode === value ? 'bg-brand-soft text-brand' : 'text-fg-muted hover:text-fg'
                  }`}
                >
                  <Icon className="size-3.5" /> {label}
                  {value === 'live' && live.agent.online && <span className="size-1.5 rounded-full bg-emerald-500" />}
                </button>
              ))}
            </div>
          )}

          {mode === 'live' && liveAvailable ? (
            <LiveChat
              agent={live.agent}
              messages={live.messages}
              identified={live.identified}
              error={live.error}
              onSend={live.send}
              onIdentify={live.identify}
              onTyping={live.markTyping}
            />
          ) : (
          <>
          <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto bg-bg p-4" aria-live="polite">
            {msgs.map((m, i) =>
              m.from === 'bot' ? (
                <div key={i} className="word-in flex items-end gap-2">
                  <span className="shrink-0">
                    <BotMascot size={28} follow={false} />
                  </span>
                  <div className="max-w-[85%] whitespace-pre-line rounded-2xl rounded-bl-sm border border-line bg-elevated px-3.5 py-2.5 text-sm leading-relaxed">
                    <RichText text={m.reply.text} />
                    {m.reply.links && (
                      <div className="mt-2.5 flex flex-wrap gap-1.5">
                        {m.reply.links.map((l) => (
                          <BotLinkChip key={l.href + l.label} {...l} />
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div key={i} className="word-in flex justify-end">
                  <div className="max-w-[82%] rounded-2xl rounded-br-sm bg-cta px-3.5 py-2.5 text-sm text-on-cta">{m.reply.text}</div>
                </div>
              ),
            )}
            {typing && (
              <div className="flex items-end gap-2">
                <BotMascot size={28} follow={false} />
                <div className="flex gap-1 rounded-2xl rounded-bl-sm border border-line bg-elevated px-4 py-3">
                  {[0, 1, 2].map((d) => (
                    <span key={d} className="bot-typing size-1.5 rounded-full bg-fg-subtle" style={{ animationDelay: `${d * 0.15}s` }} />
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="border-t border-line bg-elevated p-3">
            <div className="mb-2 flex max-h-28 flex-wrap gap-1.5 overflow-y-auto pr-1">
              <button
                type="button"
                onClick={() => ask('Menu')}
                className="inline-flex shrink-0 items-center gap-1 rounded-full bg-brand-soft px-3 py-1 text-xs font-semibold text-brand transition hover:bg-cta hover:text-on-cta"
              >
                <LayoutGrid className="size-3" /> Menu
              </button>
              {suggestions.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => ask(q)}
                  className="shrink-0 rounded-full border border-line px-3 py-1 text-xs font-medium text-fg-muted transition hover:border-brand hover:text-brand"
                >
                  {q}
                </button>
              ))}
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                ask(input);
              }}
              className="flex items-center gap-2"
            >
              <input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                maxLength={300}
                placeholder="Ask about products, pricing, scraping…"
                aria-label="Your question"
                className="h-11 min-w-0 flex-1 rounded-full border border-line bg-bg px-4 text-sm outline-none transition focus:border-brand"
              />
              <button type="submit" aria-label="Send" disabled={!input.trim() || typing} className="grid size-11 shrink-0 place-items-center rounded-full bg-cta text-on-cta transition hover:bg-cta-hover disabled:opacity-50">
                <Send className="size-4" />
              </button>
            </form>
            {liveAvailable ? (
              <button type="button" onClick={() => setMode('live')} className="mt-2 flex w-full items-center justify-center gap-1.5 text-[11px] text-fg-subtle hover:text-brand">
                <MessageCircle className="size-3.5 text-brand" /> Prefer a human? Chat with the team live
              </button>
            ) : (
              <a href={whatsappLink()} target="_blank" rel="noopener noreferrer" className="mt-2 flex items-center justify-center gap-1.5 text-[11px] text-fg-subtle hover:text-brand">
                <WhatsappIcon className="size-3.5 text-[#25d366]" /> Prefer a human? Chat with the team on WhatsApp
              </a>
            )}
          </div>
          </>
          )}
        </div>
      )}
    </>
  );
}
