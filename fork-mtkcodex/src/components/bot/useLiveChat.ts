'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

/** Browser side of the live chat: token, messages, polling and presence. */

export type ChatMessage = {
  id: string | number;
  direction: 'in' | 'out';
  sender: '' | 'customer' | 'agent' | 'bot';
  body: string;
  created_at: string;
  pending?: boolean;
};

export type Agent = { name: string; online: boolean; typing?: boolean };

const TOKEN_KEY = 'mtk-chat-token-v1';
const SEEN_KEY = 'mtk-chat-seen-v1';

function readStorage(key: string): string {
  try {
    return window.localStorage.getItem(key) || '';
  } catch {
    return '';
  }
}

function writeStorage(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // Private mode: the chat still works for this page view.
  }
}

const browserTimezone = () => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || '';
  } catch {
    return '';
  }
};

async function call<T>(url: string, init: RequestInit & { token?: string } = {}): Promise<T> {
  const { token, ...rest } = init;
  const res = await fetch(url, {
    ...rest,
    headers: { 'Content-Type': 'application/json', ...(token ? { 'x-chat-token': token } : {}), ...(rest.headers || {}) },
    cache: 'no-store',
  });
  const data = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (!res.ok) throw Object.assign(new Error(data.error || `HTTP ${res.status}`), { status: res.status });
  return data;
}

export function useLiveChat({ active, pathname }: { active: boolean; pathname: string }) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [agent, setAgent] = useState<Agent>({ name: 'Kashif', online: false });
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [identified, setIdentified] = useState(false);
  const [unread, setUnread] = useState(0);
  const [error, setError] = useState('');
  const [hasSession, setHasSession] = useState(false);
  const token = useRef('');
  const typingAt = useRef(0);
  // Last time anything happened in the chat; drives the polling speed.
  const lastActivity = useRef(0);
  const activeRef = useRef(active);
  useEffect(() => {
    activeRef.current = active;
  }, [active]);

  const merge = useCallback((incoming: ChatMessage[]) => {
    if (!incoming.length) return;
    setMessages((current) => {
      const ids = new Set(current.filter((m) => !m.pending).map((m) => String(m.id)));
      const fresh = incoming.filter((m) => !ids.has(String(m.id)));
      if (!fresh.length) return current;
      // Replace optimistic bubbles with the stored copies.
      const withoutPending = current.filter((m) => !m.pending || !fresh.some((f) => f.direction === 'in' && f.body === m.body));
      return [...withoutPending, ...fresh].sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
    });
    lastActivity.current = Date.now();
    const replies = incoming.filter((m) => m.direction === 'out');
    if (replies.length && !activeRef.current) setUnread((n) => n + replies.length);
    if (replies.length) writeStorage(SEEN_KEY, replies[replies.length - 1].created_at);
  }, []);

  const lastAt = useCallback(
    () => messages.filter((m) => !m.pending).reduce((max, m) => (m.created_at > max ? m.created_at : max), ''),
    [messages],
  );

  // Status, a saved chat, or a "continue the chat" link from an email.
  useEffect(() => {
    lastActivity.current = Date.now();
    token.current = readStorage(TOKEN_KEY);
    setHasSession(Boolean(token.current));
    call<{ enabled: boolean; agent: Agent }>('/api/chat/status')
      .then((data) => {
        setEnabled(data.enabled);
        setAgent(data.agent);
      })
      .catch(() => setEnabled(false));

    const params = new URLSearchParams(window.location.search);
    const resume = params.get('chat');
    if (resume) {
      params.delete('chat');
      const query = params.toString();
      window.history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`);
      call<{ token: string; messages: ChatMessage[]; agent: Agent }>('/api/chat/start', {
        method: 'POST',
        body: JSON.stringify({ resume, page: window.location.pathname }),
      })
        .then((data) => {
          token.current = data.token;
          writeStorage(TOKEN_KEY, data.token);
          setHasSession(true);
          setMessages(data.messages);
          setAgent(data.agent);
          window.dispatchEvent(new CustomEvent('mtk-chat-open'));
        })
        .catch(() => undefined);
    }
  }, []);

  const poll = useCallback(async () => {
    if (!token.current) return;
    const typing = Date.now() - typingAt.current < 4000;
    try {
      const after = lastAt();
      const data = await call<{ messages: ChatMessage[]; agent: Agent; identified: boolean }>(
        `/api/chat/poll?${new URLSearchParams({ ...(after ? { after } : {}), ...(typing ? { typing: '1' } : {}) })}`,
        { token: token.current },
      );
      merge(data.messages);
      setAgent(data.agent);
      setIdentified(data.identified);
    } catch (err) {
      if ((err as { status?: number }).status === 401) {
        // Token no longer valid (rotated by a resume link elsewhere): start fresh next time.
        token.current = '';
        writeStorage(TOKEN_KEY, null);
        setHasSession(false);
      }
    }
  }, [lastAt, merge]);

  // Adaptive polling keeps serverless usage low (each poll is one function call):
  // 3 s mid-conversation, 8 s when open but quiet, 30 s in the background for the
  // unread badge, and no background polling after 30 quiet minutes.
  useEffect(() => {
    if (!hasSession) return;
    let timer = 0;
    let stopped = false;
    const schedule = () => {
      const idle = Date.now() - lastActivity.current;
      const delay = active ? (idle < 2 * 60_000 ? 3_000 : 8_000) : idle < 30 * 60_000 ? 30_000 : 0;
      if (!delay || stopped) return;
      timer = window.setTimeout(async () => {
        if (document.visibilityState === 'visible') await poll();
        schedule();
      }, delay);
    };
    void poll().then(schedule);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [active, hasSession, poll]);

  useEffect(() => {
    if (!active) return;
    setUnread(0);
    lastActivity.current = Date.now();
  }, [active]);

  const ensureSession = useCallback(async () => {
    if (token.current) return token.current;
    const data = await call<{ token: string; agent: Agent }>('/api/chat/start', {
      method: 'POST',
      body: JSON.stringify({ page: pathname, referrer: document.referrer, timezone: browserTimezone() }),
    });
    token.current = data.token;
    writeStorage(TOKEN_KEY, data.token);
    setHasSession(true);
    setAgent(data.agent);
    return data.token;
  }, [pathname]);

  const send = useCallback(
    async (body: string) => {
      const text = body.trim().slice(0, 2000);
      if (!text) return;
      setError('');
      lastActivity.current = Date.now();
      const optimistic: ChatMessage = { id: `local-${Date.now()}`, direction: 'in', sender: 'customer', body: text, created_at: new Date().toISOString(), pending: true };
      setMessages((m) => [...m, optimistic]);
      try {
        const t = await ensureSession();
        const data = await call<{ messages: ChatMessage[] }>('/api/chat/send', { method: 'POST', token: t, body: JSON.stringify({ body: text }) });
        setMessages((m) => m.filter((x) => x.id !== optimistic.id));
        merge(data.messages);
      } catch (err) {
        setMessages((m) => m.filter((x) => x.id !== optimistic.id));
        setError(err instanceof Error ? err.message : 'Message not sent');
        throw err;
      }
    },
    [ensureSession, merge],
  );

  const identify = useCallback(
    async (details: { name: string; email: string; phone: string; preferred_channel: string; website?: string }) => {
      const t = await ensureSession();
      await call('/api/chat/identify', { method: 'POST', token: t, body: JSON.stringify(details) });
      setIdentified(true);
    },
    [ensureSession],
  );

  const markTyping = useCallback(() => {
    typingAt.current = Date.now();
    lastActivity.current = Date.now();
  }, []);

  return { enabled, agent, messages, identified, unread, error, setError, send, identify, markTyping, hasSession };
}
