import { createHash, createHmac, randomBytes, randomUUID, timingSafeEqual } from 'node:crypto';
import { mutateTable, readTable } from '@/lib/file-store';
import { supabase } from '@/lib/supabase';
import {
  addActivities,
  blankLead,
  findLeadByEmail,
  findLeadByPhone,
  getLead,
  LeadError,
  storageMode,
  writeLeadChanges,
  type NewActivity,
} from '@/lib/leads';
import { normalizePhone, type Lead, type Message, type PreferredChannel } from '@/lib/lead-types';
import { insertMessage, linkThreadToLead, listThread } from '@/lib/message-store';
import { adminOnline, notifyOwner } from '@/lib/notify';
import { emailConfigured, replyAddress, sendEmail } from '@/lib/email';
import { offlineNotice } from '@/lib/business-hours';
import type { Geo } from '@/lib/geo';

/**
 * Website live chat. A visitor holds a random token (kept in their browser);
 * only its SHA-256 is stored. Messages live in the shared `messages` table
 * under thread `web:<session id>` so the owner answers from the same inbox.
 */

export type ChatSession = {
  id: string;
  token_hash: string;
  lead_id: string | null;
  name: string;
  email: string;
  phone: string;
  preferred_channel: string;
  page: string;
  referrer: string;
  device: string;
  city: string;
  region: string;
  country: string;
  timezone: string;
  lat: number | null;
  lng: number | null;
  status: 'open' | 'closed';
  unread_admin: number;
  last_seen_at: string;
  visitor_typing_at: string | null;
  admin_typing_at: string | null;
  last_message_at: string | null;
  last_notified_at: string | null;
  created_at: string;
};

/** What the visitor's browser may see about a message. */
export type PublicMessage = Pick<Message, 'id' | 'direction' | 'sender' | 'body' | 'created_at'>;

const VISITOR_ONLINE_MS = 45_000;
const TYPING_MS = 6_000;
const NOTIFY_EVERY_MS = 3 * 60 * 1000;

export const agentName = () => (process.env.CHAT_AGENT_NAME || 'Kashif').trim();
const hashToken = (token: string) => createHash('sha256').update(token).digest('hex');
const siteUrl = () => (process.env.NEXT_PUBLIC_SITE_URL || 'https://mtkcodex.tech').replace(/\/+$/, '');

export function toPublic(message: Message): PublicMessage {
  return { id: message.id, direction: message.direction, sender: message.sender, body: message.body, created_at: message.created_at };
}

/* ---------------------------------------------------------------------------
 * Session storage
 * ------------------------------------------------------------------------- */

export async function createChatSession(input: { geo: Geo; page: string; referrer: string; device: string; timezone?: string }) {
  if (storageMode() === 'readonly') throw new LeadError('Live chat needs the database.', 503);
  const token = randomBytes(24).toString('base64url');
  const now = new Date().toISOString();
  const session: ChatSession = {
    id: randomUUID(),
    token_hash: hashToken(token),
    lead_id: null,
    name: '',
    email: '',
    phone: '',
    preferred_channel: '',
    page: input.page.slice(0, 200),
    referrer: input.referrer.slice(0, 120),
    device: input.device,
    city: input.geo.city,
    region: input.geo.region,
    country: input.geo.country,
    // Prefer the edge timezone; fall back to the browser's own report.
    timezone: input.geo.timezone || input.timezone || '',
    lat: input.geo.lat,
    lng: input.geo.lng,
    status: 'open',
    unread_admin: 0,
    last_seen_at: now,
    visitor_typing_at: null,
    admin_typing_at: null,
    last_message_at: null,
    last_notified_at: null,
    created_at: now,
  };
  if (storageMode() === 'supabase') {
    await supabase('chat_sessions', { method: 'POST', headers: { Prefer: 'return=minimal' }, body: JSON.stringify(session) });
  } else {
    await mutateTable<ChatSession, void>('chats', (rows) => {
      rows.push(session);
    });
  }
  return { token, session };
}

export async function chatSessionByToken(token: unknown): Promise<ChatSession | null> {
  if (typeof token !== 'string' || token.length < 20 || token.length > 100 || storageMode() === 'readonly') return null;
  const hash = hashToken(token);
  if (storageMode() === 'supabase') {
    const rows = await supabase<ChatSession[]>(`chat_sessions?token_hash=eq.${hash}&select=*`);
    return rows[0] || null;
  }
  return (await readTable<ChatSession>('chats')).find((s) => s.token_hash === hash) || null;
}

export async function getChatSession(id: string): Promise<ChatSession | null> {
  if (!/^[0-9a-f-]{36}$/i.test(id) || storageMode() === 'readonly') return null;
  if (storageMode() === 'supabase') {
    const rows = await supabase<ChatSession[]>(`chat_sessions?id=eq.${id}&select=*`);
    return rows[0] || null;
  }
  return (await readTable<ChatSession>('chats')).find((s) => s.id === id) || null;
}

export async function updateChatSession(id: string, changes: Partial<ChatSession>): Promise<void> {
  if (storageMode() === 'supabase') {
    await supabase(`chat_sessions?id=eq.${id}`, { method: 'PATCH', body: JSON.stringify(changes) });
    return;
  }
  await mutateTable<ChatSession, void>('chats', (rows) => {
    const row = rows.find((s) => s.id === id);
    if (row) Object.assign(row, changes);
  });
}

/** Sessions with at least one message, newest first. */
export async function listChatSessions(limit = 200): Promise<ChatSession[]> {
  if (storageMode() === 'readonly') return [];
  if (storageMode() === 'supabase') {
    return supabase<ChatSession[]>(
      `chat_sessions?last_message_at=not.is.null&select=*&order=last_message_at.desc&limit=${limit}`,
    );
  }
  return (await readTable<ChatSession>('chats'))
    .filter((s) => s.last_message_at)
    .sort((a, b) => (b.last_message_at || '').localeCompare(a.last_message_at || ''))
    .slice(0, limit);
}

export function visitorOnline(session: Pick<ChatSession, 'last_seen_at'>, now = Date.now()): boolean {
  return now - new Date(session.last_seen_at).getTime() < VISITOR_ONLINE_MS;
}

/* ---------------------------------------------------------------------------
 * Visitor side
 * ------------------------------------------------------------------------- */

export async function visitorSend(session: ChatSession, body: string): Promise<PublicMessage[]> {
  const text = body.trim().slice(0, 2000);
  if (!text) throw new LeadError('Message is empty.');
  const threadKey = `web:${session.id}`;
  const now = new Date().toISOString();

  const message = await insertMessage({
    lead_id: session.lead_id,
    channel: 'web',
    thread_key: threadKey,
    direction: 'in',
    sender: 'customer',
    msg_type: 'text',
    body: text,
    external_id: null,
    status: 'received',
  });
  const out: PublicMessage[] = message ? [toPublic(message)] : [];

  const firstMessage = !session.last_message_at;
  const notifyDue = !session.last_notified_at || Date.now() - new Date(session.last_notified_at).getTime() > NOTIFY_EVERY_MS;
  await updateChatSession(session.id, {
    unread_admin: session.unread_admin + 1,
    last_message_at: now,
    last_seen_at: now,
    visitor_typing_at: null,
    ...(notifyDue ? { last_notified_at: now } : {}),
  });

  if (session.lead_id) {
    const lead = await getLead(session.lead_id);
    if (lead) {
      await writeLeadChanges(lead.id, { last_inbound_at: now });
      await addActivities([{ lead_id: lead.id, kind: 'message_in', summary: text.slice(0, 200), meta: { channel: 'web' } }]);
    }
  }

  // When nobody is at the inbox, answer straight away in the visitor's own time.
  if (!(await adminOnline())) {
    const history = await listThread(threadKey, { limit: 30 });
    const recentBot = history.some(
      (m) => m.sender === 'bot' && Date.now() - new Date(m.created_at).getTime() < 30 * 60 * 1000,
    );
    if (!recentBot) {
      const notice = await insertMessage({
        lead_id: session.lead_id,
        channel: 'web',
        thread_key: threadKey,
        direction: 'out',
        sender: 'bot',
        msg_type: 'text',
        body: offlineNotice(session.timezone, { email: session.email }),
        external_id: null,
        status: 'sent',
      });
      if (notice) out.push(toPublic(notice));
    }
  }

  if (notifyDue) {
    const where = [session.city, session.country].filter(Boolean).join(', ');
    await notifyOwner({
      title: `${firstMessage ? 'New chat' : 'Chat'} · ${session.name || `Visitor${where ? ` from ${where}` : ''}`}`,
      body: text,
      url: `/admin/inbox?key=web:${session.id}`,
      tag: `web:${session.id}`,
    });
  }
  return out;
}

export async function pollChat(session: ChatSession, after: string | null, typing: boolean) {
  const now = new Date().toISOString();
  await updateChatSession(session.id, { last_seen_at: now, ...(typing ? { visitor_typing_at: now } : {}) });
  const messages = await listThread(`web:${session.id}`, { after: after || undefined, limit: 100 });
  return {
    messages: messages.map(toPublic),
    agent: {
      name: agentName(),
      online: await adminOnline(),
      typing: Boolean(session.admin_typing_at && Date.now() - new Date(session.admin_typing_at).getTime() < TYPING_MS),
    },
    identified: Boolean(session.email || session.phone),
  };
}

export type VisitorDetails = { name: string; email: string; phone: string; preferred_channel: PreferredChannel };

/** Saves the visitor's contact details and links (or creates) their CRM lead. */
export async function identifyVisitor(session: ChatSession, details: VisitorDetails): Promise<Lead> {
  const email = details.email.trim().toLowerCase().slice(0, 200);
  const phone = normalizePhone(details.phone);
  const name = details.name.trim().slice(0, 120);
  if (!email && !phone) throw new LeadError('Add an email or phone number so we can reply.');
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) throw new LeadError('That email address looks incomplete.');

  let lead = (session.lead_id && (await getLead(session.lead_id))) || (email && (await findLeadByEmail(email))) || (phone && (await findLeadByPhone(phone))) || null;
  const activities: NewActivity[] = [];
  const place = { city: session.city, region: session.region, country: session.country, timezone: session.timezone };

  if (!lead) {
    lead = blankLead(
      {
        name: name || email || phone,
        email,
        phone,
        status: 'replied',
        starred: true,
        channel: 'web',
        preferred_channel: details.preferred_channel || 'chat',
        notes: `Contact: ${name || '—'}\nStarted a live chat on ${session.page || 'the website'}.`,
        tags: ['live-chat'],
        lead_tier: 'A',
        ...place,
      },
      'web_chat',
    );
    if (storageMode() === 'supabase') {
      await supabase('leads?on_conflict=id', {
        method: 'POST',
        headers: { Prefer: 'resolution=ignore-duplicates,return=minimal' },
        body: JSON.stringify(lead),
      });
    } else {
      const created = lead;
      await mutateTable<Lead, void>('leads', (rows) => {
        rows.unshift(created);
      });
    }
    activities.push({ lead_id: lead.id, kind: 'created', summary: `New lead from live chat${place.city ? ` (${place.city}, ${place.country})` : ''}` });
  } else {
    const fill: Partial<Lead> = { starred: true };
    if (!lead.email && email) fill.email = email;
    if (!lead.phone && phone) fill.phone = phone;
    if (!lead.city && place.city) Object.assign(fill, place);
    if (details.preferred_channel) fill.preferred_channel = details.preferred_channel;
    lead = await writeLeadChanges(lead.id, fill);
    activities.push({ lead_id: lead.id, kind: 'edit', summary: 'Identified in live chat' });
  }

  await updateChatSession(session.id, {
    lead_id: lead.id,
    name: name || session.name,
    email: email || session.email,
    phone: phone || session.phone,
    preferred_channel: details.preferred_channel || session.preferred_channel,
  });
  await linkThreadToLead(`web:${session.id}`, lead.id);
  await addActivities(activities);
  await notifyOwner({
    title: `Chat lead · ${name || email || phone}`,
    body: `${[email, phone].filter(Boolean).join(' · ')}${place.city ? ` — ${place.city}, ${place.country}` : ''}`,
    url: `/admin/inbox?key=web:${session.id}`,
    tag: `web:${session.id}`,
  });
  return lead;
}

/* ---------------------------------------------------------------------------
 * Owner side
 * ------------------------------------------------------------------------- */

export async function setAgentTyping(sessionId: string): Promise<void> {
  await updateChatSession(sessionId, { admin_typing_at: new Date().toISOString() });
}

/** Owner reply in a live chat. If the visitor has left, it is emailed too. */
export async function sendAgentReply(sessionId: string, text: string): Promise<Message> {
  const session = await getChatSession(sessionId);
  if (!session) throw new LeadError('Chat not found.', 404);
  const lead = session.lead_id ? await getLead(session.lead_id) : null;
  if (lead?.do_not_contact) throw new LeadError('This visitor opted out. Messaging is blocked.', 409);

  const away = !visitorOnline(session);
  let emailed = false;
  if (away && session.email && emailConfigured()) {
    try {
      await sendEmail({
        to: session.email,
        subject: `${agentName()} from MTK Codex replied to your chat`,
        text: `${text}\n\n— ${agentName()}, MTK Codex\n\nContinue the chat: ${chatResumeUrl(session.id)}\nOr simply reply to this email.`,
        replyTo: replyAddress(lead?.contact_token) || undefined,
      });
      emailed = true;
    } catch (error) {
      console.error('chat: reply email failed', error instanceof Error ? error.message : error);
    }
  }

  const message = await insertMessage({
    lead_id: session.lead_id,
    channel: 'web',
    thread_key: `web:${session.id}`,
    direction: 'out',
    sender: 'agent',
    msg_type: 'text',
    body: text,
    external_id: null,
    status: emailed ? 'delivered' : 'sent',
    meta: emailed ? { emailed: true } : {},
  });
  await updateChatSession(session.id, { admin_typing_at: null, unread_admin: 0, last_message_at: new Date().toISOString() });
  if (lead) {
    await writeLeadChanges(lead.id, { last_outbound_at: new Date().toISOString(), unread_count: 0 });
    await addActivities([{ lead_id: lead.id, kind: 'message_out', summary: text.slice(0, 200), meta: { channel: 'web', emailed } }]);
  }
  if (!message) throw new Error('Could not store the reply.');
  return message;
}

/* ---------------------------------------------------------------------------
 * "Continue the chat" links in emails (signed, 14 days)
 * ------------------------------------------------------------------------- */

const resumeSecret = () => (process.env.ADMIN_SESSION_SECRET || '').trim();

function resumeSignature(id: string, exp: number) {
  return createHmac('sha256', resumeSecret()).update(`chat:${id}:${exp}`).digest('base64url').slice(0, 32);
}

export function chatResumeUrl(sessionId: string): string {
  const exp = Math.floor(Date.now() / 1000) + 14 * 86_400;
  return `${siteUrl()}/?chat=${sessionId}.${exp}.${resumeSignature(sessionId, exp)}`;
}

/** Validates a resume code and issues a fresh visitor token for that chat. */
export async function resumeChat(code: string): Promise<{ token: string; session: ChatSession } | null> {
  const [id, expRaw, sig] = code.split('.');
  const exp = Number(expRaw);
  if (!id || !sig || !Number.isFinite(exp) || exp < Date.now() / 1000 || !resumeSecret()) return null;
  const expected = Buffer.from(resumeSignature(id, exp));
  const given = Buffer.from(sig);
  if (expected.length !== given.length || !timingSafeEqual(expected, given)) return null;
  const session = await getChatSession(id);
  if (!session) return null;
  const token = randomBytes(24).toString('base64url');
  await updateChatSession(id, { token_hash: hashToken(token), last_seen_at: new Date().toISOString() });
  return { token, session };
}
