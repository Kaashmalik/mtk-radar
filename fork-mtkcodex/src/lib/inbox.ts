import { randomBytes, randomUUID } from 'node:crypto';
import { mutateTable, readTable } from '@/lib/file-store';
import { inList, supabase } from '@/lib/supabase';
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
import {
  CONTACTED_STATUSES,
  STATUS_LABELS,
  phoneDigits,
  threadChannel,
  todayPKT,
  waWindowOpen,
  type Conversation,
  type Lead,
  type Message,
} from '@/lib/lead-types';
import {
  defaultTemplate,
  isOptOut,
  sendTemplate,
  sendText,
  whatsappConfigured,
  type InboundMessage,
  type StatusUpdate,
} from '@/lib/whatsapp';
import {
  emailConfigured,
  getReceivedEmail,
  htmlToText,
  parseAddress,
  replyAddress,
  sendEmail,
  stripQuotedReply,
  tokenFromRecipients,
} from '@/lib/email';
import { notifyOwner } from '@/lib/notify';
import { listChatSessions, sendAgentReply, updateChatSession, type ChatSession } from '@/lib/chat';
import { insertMessage, listThread, type NewMessage } from '@/lib/message-store';

export { insertMessage, linkThreadToLead, listThread } from '@/lib/message-store';

/**
 * One inbox for every channel. Messages share a table keyed by thread:
 *   web:<chat session id> · wa:<digits> · email:<address>
 */

async function leadsById(ids: string[]): Promise<Map<string, Lead>> {
  const unique = [...new Set(ids.filter(Boolean))];
  const leads: Lead[] = [];
  if (!unique.length) return new Map();
  if (storageMode() === 'supabase') {
    for (let i = 0; i < unique.length; i += 150) {
      leads.push(
        ...(await supabase<Lead[]>(
          `leads?id=${encodeURIComponent(inList(unique.slice(i, i + 150)))}&select=id,name,email,phone,status,do_not_contact,unread_count,last_inbound_at,city,region,country,timezone`,
        )),
      );
    }
  } else {
    const set = new Set(unique);
    leads.push(...(await readTable<Lead>('leads')).filter((lead) => set.has(lead.id)));
  }
  return new Map(leads.map((lead) => [lead.id, lead]));
}

const ONLINE_MS = 45_000;

export async function listConversations(): Promise<Conversation[]> {
  const mode = storageMode();
  if (mode === 'readonly') return [];

  const recent =
    mode === 'supabase'
      ? await supabase<Message[]>(
          'messages?select=id,thread_key,channel,lead_id,direction,body,subject,created_at&order=created_at.desc&limit=4000',
        )
      : (await readTable<Message>('messages')).sort((a, b) => b.created_at.localeCompare(a.created_at));

  const latest = new Map<string, Message>();
  const lastInbound = new Map<string, string>();
  const leadIds = new Map<string, string>();
  for (const message of recent) {
    if (!latest.has(message.thread_key)) latest.set(message.thread_key, message);
    if (message.direction === 'in' && !lastInbound.has(message.thread_key)) lastInbound.set(message.thread_key, message.created_at);
    if (message.lead_id && !leadIds.has(message.thread_key)) leadIds.set(message.thread_key, message.lead_id);
  }

  const sessions = new Map<string, ChatSession>();
  if ([...latest.keys()].some((key) => key.startsWith('web:'))) {
    for (const session of await listChatSessions(300)) sessions.set(`web:${session.id}`, session);
  }
  for (const session of sessions.values()) if (session.lead_id) leadIds.set(`web:${session.id}`, session.lead_id);
  const leads = await leadsById([...leadIds.values()]);
  const now = Date.now();

  return [...latest.values()].map((message): Conversation => {
    const key = message.thread_key;
    const channel = threadChannel(key) || message.channel;
    const lead = leads.get(leadIds.get(key) || '');
    const session = sessions.get(key);
    const address = key.slice(key.indexOf(':') + 1);
    const name =
      lead?.name ||
      session?.name ||
      (channel === 'web' ? `Visitor${session?.city ? ` from ${session.city}` : ''}` : channel === 'whatsapp' ? `+${address}` : address);
    const place = session
      ? { city: session.city, region: session.region, country: session.country, timezone: session.timezone }
      : lead
        ? { city: lead.city || '', region: lead.region || '', country: lead.country || '', timezone: lead.timezone || '' }
        : undefined;
    return {
      key,
      channel,
      lead_id: lead?.id ?? null,
      name,
      subtitle: channel === 'email' ? message.subject || address : channel === 'whatsapp' ? `+${address}` : session?.email || session?.page || '',
      last_body: message.body,
      last_direction: message.direction,
      last_at: message.created_at,
      last_inbound_at: lastInbound.get(key) || lead?.last_inbound_at || null,
      unread: channel === 'web' ? session?.unread_admin || 0 : lead?.unread_count || 0,
      do_not_contact: Boolean(lead?.do_not_contact),
      status: lead?.status ?? null,
      online: channel === 'web' && session ? now - new Date(session.last_seen_at).getTime() < ONLINE_MS : undefined,
      place,
    };
  });
}

/* ---------------------------------------------------------------------------
 * Leads touched by inbound messages
 * ------------------------------------------------------------------------- */

async function insertLead(lead: Lead): Promise<void> {
  if (storageMode() === 'supabase') {
    await supabase('leads?on_conflict=id', {
      method: 'POST',
      headers: { Prefer: 'resolution=ignore-duplicates,return=minimal' },
      body: JSON.stringify(lead),
    });
    return;
  }
  await mutateTable<Lead, void>('leads', (rows) => {
    if (!rows.some((row) => row.id === lead.id)) rows.unshift(lead);
  });
}

/** Moves a lead to "replied", bumps unread, logs the message and handles STOP. */
async function applyInbound(lead: Lead, body: string, at: string, channel: string, extra: NewActivity[] = []) {
  const activities: NewActivity[] = [...extra];
  const changes: Partial<Lead> = { last_inbound_at: at, unread_count: (lead.unread_count || 0) + 1 };
  if (['new', 'queued', 'contacted', 'skipped'].includes(lead.status)) {
    changes.status = 'replied';
    activities.push({
      lead_id: lead.id,
      kind: 'status',
      summary: `Status: ${STATUS_LABELS[lead.status]} → ${STATUS_LABELS.replied} (customer replied)`,
      meta: { from: lead.status, to: 'replied', auto: true },
    });
  }
  activities.push({ lead_id: lead.id, kind: 'message_in', summary: body.slice(0, 200), meta: { channel } });
  if (isOptOut(body) || /^\s*unsubscribe\b/i.test(body)) {
    if (!lead.do_not_contact) {
      changes.do_not_contact = true;
      activities.push({ lead_id: lead.id, kind: 'opt_out', summary: `Opted out by replying "${body.trim().slice(0, 40)}"`, meta: { auto: true } });
    }
  }
  await writeLeadChanges(lead.id, changes);
  await addActivities(activities);
}

/* ---------------------------------------------------------------------------
 * WhatsApp
 * ------------------------------------------------------------------------- */

export async function recordInboundWhatsApp(message: InboundMessage): Promise<void> {
  if (storageMode() === 'readonly') return;
  let lead = await findLeadByPhone(message.from);
  const extra: NewActivity[] = [];
  if (!lead) {
    lead = blankLead(
      { name: message.profileName || `+${message.from}`, phone: `+${message.from}`, status: 'replied', preferred_channel: 'whatsapp' },
      'whatsapp',
    );
    lead.id = `wa:${message.from}`;
    await insertLead(lead);
    extra.push({ lead_id: lead.id, kind: 'created', summary: 'New lead from an inbound WhatsApp chat' });
  }

  const stored = await insertMessage({
    lead_id: lead.id,
    channel: 'whatsapp',
    thread_key: `wa:${message.from}`,
    direction: 'in',
    sender: 'customer',
    msg_type: message.type,
    body: message.body,
    external_id: message.wamid,
    status: 'received',
    created_at: message.timestamp,
  });
  if (!stored) return; // duplicate webhook delivery

  await applyInbound(lead, message.body, message.timestamp, 'whatsapp', extra);
  await notifyOwner({ title: `WhatsApp · ${lead.name}`, body: message.body, url: `/admin/inbox?key=wa:${message.from}`, tag: `wa:${message.from}` });
}

const STATUS_ORDER = ['sent', 'delivered', 'read'] as const;

/** Delivery receipts only move forward (sent → delivered → read); failures always apply. */
export async function applyWhatsAppStatus(update: StatusUpdate): Promise<void> {
  if (!update.wamid || storageMode() === 'readonly') return;
  const earlier =
    update.status === 'failed'
      ? ['sent', 'delivered']
      : STATUS_ORDER.slice(0, STATUS_ORDER.indexOf(update.status as (typeof STATUS_ORDER)[number]));
  if (!earlier.length) return;
  const changes = { status: update.status, error: update.error };
  if (storageMode() === 'supabase') {
    await supabase(
      `messages?external_id=eq.${encodeURIComponent(update.wamid)}&status=${encodeURIComponent(inList(earlier))}`,
      { method: 'PATCH', body: JSON.stringify(changes) },
    );
    return;
  }
  await mutateTable<Message, void>('messages', (rows) => {
    const row = rows.find((item) => item.external_id === update.wamid);
    if (row && earlier.includes(row.status)) Object.assign(row, changes);
  });
}

/* ---------------------------------------------------------------------------
 * Email
 * ------------------------------------------------------------------------- */

async function leadByContactToken(token: string): Promise<Lead | null> {
  if (storageMode() === 'supabase') {
    const rows = await supabase<Lead[]>(`leads?contact_token=eq.${encodeURIComponent(token)}&select=*&limit=1`);
    return rows[0] || null;
  }
  return (await readTable<Lead>('leads')).find((lead) => lead.contact_token === token) || null;
}

/** Gives a lead its private reply-address token on first use. */
async function ensureContactToken(lead: Lead): Promise<string> {
  if (lead.contact_token) return lead.contact_token;
  const token = randomBytes(9).toString('base64url').toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 12).padEnd(12, '0');
  await writeLeadChanges(lead.id, { contact_token: token });
  return token;
}

/** Handles Resend's `email.received` webhook for one email id. */
export async function recordInboundEmail(emailId: string): Promise<void> {
  if (storageMode() === 'readonly') return;
  const email = await getReceivedEmail(emailId);
  const { name, email: from } = parseAddress(email.from);
  if (!from) return;

  const token = tokenFromRecipients(email.to || []);
  let lead = (token && (await leadByContactToken(token))) || (await findLeadByEmail(from));
  const extra: NewActivity[] = [];
  if (!lead) {
    lead = blankLead({ name: name || from, email: from, status: 'replied', channel: 'email', preferred_channel: 'email' }, 'email');
    await insertLead(lead);
    extra.push({ lead_id: lead.id, kind: 'created', summary: `New lead from an email to ${email.to?.[0] || 'the inbox'}` });
  }

  const raw = email.text || (email.html ? htmlToText(email.html) : '');
  const body = (stripQuotedReply(raw) || raw).slice(0, 8000);
  const stored = await insertMessage({
    lead_id: lead.id,
    channel: 'email',
    thread_key: `email:${from}`,
    direction: 'in',
    sender: 'customer',
    msg_type: 'email',
    subject: (email.subject || '').slice(0, 300),
    body: body || '(empty email)',
    external_id: `email:${email.id}`,
    status: 'received',
    meta: {
      message_id: email.message_id,
      attachments: (email.attachments || []).map((a) => a.filename),
      auth: email.authentication || null,
    },
    created_at: email.created_at || new Date().toISOString(),
  });
  if (!stored) return;

  await applyInbound(lead, body, stored.created_at, 'email', extra);
  await notifyOwner({
    title: `Email · ${lead.name}`,
    body: `${email.subject ? `${email.subject} — ` : ''}${body}`,
    url: `/admin/inbox?key=${encodeURIComponent(`email:${from}`)}`,
    tag: `email:${from}`,
  });

  const forwardTo = (process.env.EMAIL_FORWARD_TO || '').trim();
  if (forwardTo && forwardTo.toLowerCase() !== from) {
    await sendEmail({
      to: forwardTo,
      subject: `Fwd: ${email.subject || '(no subject)'} — from ${email.from}`,
      text: `Forwarded by the MTK Codex CRM.\nFrom: ${email.from}\nTo: ${(email.to || []).join(', ')}\n\n${raw}`,
      replyTo: from,
    }).catch((error) => console.error('email: forward failed', error instanceof Error ? error.message : error));
  }
}

/* ---------------------------------------------------------------------------
 * Sending from the dashboard
 * ------------------------------------------------------------------------- */

export type SendInput = {
  key: string;
  text?: string;
  subject?: string;
  template?: { name: string; language: string; params?: string[] };
};

async function recordOutbound(lead: Lead | null, message: NewMessage, summary: string, channel: string) {
  const stored = await insertMessage(message);
  if (!lead) return stored;
  const now = new Date().toISOString();
  const changes: Partial<Lead> = { last_outbound_at: now, last_contacted: todayPKT(), unread_count: 0 };
  const activities: NewActivity[] = [{ lead_id: lead.id, kind: 'message_out', summary: summary.slice(0, 200), meta: { channel } }];
  if (!CONTACTED_STATUSES.includes(lead.status)) {
    changes.status = 'contacted';
    activities.push({
      lead_id: lead.id,
      kind: 'status',
      summary: `Status: ${STATUS_LABELS[lead.status]} → ${STATUS_LABELS.contacted}`,
      meta: { from: lead.status, to: 'contacted', auto: true },
    });
  }
  await writeLeadChanges(lead.id, changes);
  await addActivities(activities);
  return stored;
}

export async function sendFromDashboard(input: SendInput): Promise<Message> {
  if (storageMode() === 'readonly') throw new LeadError('Connect the database before sending.', 503);
  const channel = threadChannel(input.key);
  const address = input.key.slice(input.key.indexOf(':') + 1);
  const text = (input.text || '').trim().slice(0, 8000);

  if (channel === 'web') {
    if (!text) throw new LeadError('Message is empty.');
    return sendAgentReply(address, text);
  }

  if (channel === 'whatsapp') {
    if (!whatsappConfigured()) throw new LeadError('WhatsApp Cloud API is not configured.', 503);
    const lead = await findLeadByPhone(address);
    if (!lead) throw new LeadError('No lead for this number.', 404);
    if (lead.do_not_contact) throw new LeadError('This lead opted out (do-not-contact). Messaging is blocked.', 409);
    const to = phoneDigits(lead.phone) || address;
    let body: string;
    let msgType = 'text';
    let wamid: string;
    if (input.template?.name) {
      const params = (input.template.params || []).map((p) => p.slice(0, 300));
      ({ wamid } = await sendTemplate(to, input.template.name, input.template.language || defaultTemplate().language, params));
      body = `[template: ${input.template.name}]${params.length ? ` ${params.join(' | ')}` : ''}`;
      msgType = 'template';
    } else {
      if (!text) throw new LeadError('Message is empty.');
      if (!waWindowOpen(lead.last_inbound_at)) {
        throw new LeadError('The 24-hour reply window is closed. WhatsApp only allows an approved template until the customer writes again.', 409);
      }
      ({ wamid } = await sendText(to, text));
      body = text;
    }
    const stored = await recordOutbound(
      lead,
      { lead_id: lead.id, channel: 'whatsapp', thread_key: `wa:${to}`, direction: 'out', sender: 'agent', msg_type: msgType, body, external_id: wamid, status: 'sent' },
      body,
      'whatsapp_api',
    );
    return stored ?? fallbackMessage(lead.id, 'whatsapp', `wa:${to}`, body);
  }

  if (channel === 'email') {
    if (!emailConfigured()) throw new LeadError('Email sending is not configured (RESEND_API_KEY and EMAIL_FROM).', 503);
    if (!text) throw new LeadError('Message is empty.');
    const lead = await findLeadByEmail(address);
    if (lead?.do_not_contact) throw new LeadError('This lead opted out (do-not-contact). Messaging is blocked.', 409);
    const history = await listThread(input.key, { limit: 50 });
    const lastIn = [...history].reverse().find((m) => m.direction === 'in');
    const lastSubject = [...history].reverse().find((m) => m.subject)?.subject || '';
    const subject =
      input.subject?.trim() || (lastSubject ? (/^re:/i.test(lastSubject) ? lastSubject : `Re: ${lastSubject}`) : `MTK Codex — ${lead?.name || 'hello'}`);
    const token = lead ? await ensureContactToken(lead) : null;
    const { id } = await sendEmail({
      to: address,
      subject,
      text,
      replyTo: replyAddress(token),
      inReplyTo: typeof lastIn?.meta?.message_id === 'string' ? lastIn.meta.message_id : undefined,
    });
    const stored = await recordOutbound(
      lead,
      { lead_id: lead?.id ?? null, channel: 'email', thread_key: input.key, direction: 'out', sender: 'agent', msg_type: 'email', subject, body: text, external_id: `email:${id}`, status: 'sent' },
      `Email: ${subject}`,
      'email',
    );
    return stored ?? fallbackMessage(lead?.id ?? null, 'email', input.key, text);
  }

  throw new LeadError('Unknown conversation.', 404);
}

function fallbackMessage(leadId: string | null, channel: Message['channel'], key: string, body: string): Message {
  return {
    id: randomUUID(),
    lead_id: leadId,
    channel,
    thread_key: key,
    direction: 'out',
    sender: 'agent',
    msg_type: 'text',
    subject: '',
    body,
    external_id: null,
    status: 'sent',
    error: '',
    meta: {},
    created_at: new Date().toISOString(),
  };
}

/** Clears unread counters when the owner opens a thread. */
export async function markThreadRead(key: string, lead: Lead | null, session: ChatSession | null): Promise<void> {
  if (session && session.unread_admin > 0) await updateChatSession(session.id, { unread_admin: 0 });
  if (lead && (lead.unread_count || 0) > 0 && !key.startsWith('web:')) await writeLeadChanges(lead.id, { unread_count: 0 });
}

/** The lead behind a thread key, if any. */
export async function leadForThread(key: string, session: ChatSession | null): Promise<Lead | null> {
  const channel = threadChannel(key);
  const address = key.slice(key.indexOf(':') + 1);
  if (channel === 'web') return session?.lead_id ? getLead(session.lead_id) : null;
  if (channel === 'whatsapp') return findLeadByPhone(address);
  if (channel === 'email') return findLeadByEmail(address);
  return null;
}
