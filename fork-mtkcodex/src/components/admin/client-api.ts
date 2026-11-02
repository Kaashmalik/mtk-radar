import type { ColumnMapping, RawRow } from '@/lib/lead-import';
import type { Conversation, Lead, LeadActivity, Message } from '@/lib/lead-types';
import type { ChannelStatus } from '@/lib/channels';

/** Fetch wrapper for the admin API: JSON in/out, errors carry the server message. */
async function api<T>(url: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers || {}) },
    cache: 'no-store',
  });
  const data = (await res.json().catch(() => ({}))) as T & { error?: string };
  if (res.status === 401) {
    window.location.assign(new URL('/admin/login', window.location.origin).href);
    throw new Error('Session expired — sign in again.');
  }
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

export type LeadPatchBody = Partial<
  Pick<
    Lead,
    | 'status'
    | 'notes'
    | 'next_followup'
    | 'last_contacted'
    | 'do_not_contact'
    | 'message'
    | 'starred'
    | 'tags'
    | 'deal_stage'
    | 'deal_value'
    | 'deal_currency'
    | 'name'
    | 'business_type'
    | 'area'
    | 'phone'
    | 'email'
    | 'website'
  >
> & { append_note?: string };

export const leadsApi = {
  list: () => api<{ leads: Lead[] }>('/api/admin/leads'),
  patch: (id: string, patch: LeadPatchBody) =>
    api<{ lead: Lead }>('/api/admin/leads', { method: 'PATCH', body: JSON.stringify({ id, ...patch }) }).then((d) => d.lead),
  bulkPatch: (ids: string[], patch: LeadPatchBody) =>
    api<{ updated: Lead[]; errors: { id: string; error: string }[] }>('/api/admin/leads', {
      method: 'PATCH',
      body: JSON.stringify({ ids, ...patch }),
    }),
  create: (lead: LeadPatchBody) =>
    api<{ lead: Lead }>('/api/admin/leads', { method: 'POST', body: JSON.stringify(lead) }).then((d) => d.lead),
  remove: (ids: string[]) =>
    api<{ deleted: number }>('/api/admin/leads', { method: 'DELETE', body: JSON.stringify({ ids }) }),
  activities: (leadId?: string) =>
    api<{ activities: (LeadActivity & { lead_name?: string })[]; error?: string }>(
      leadId ? `/api/admin/activities?lead=${encodeURIComponent(leadId)}` : '/api/admin/activities',
    ),
};

export type ImportSummary = { inserted: number; updated: number; skipped: number; duplicates: number; invalid: number };

export const importApi = {
  rows: (rows: RawRow[], mapping: ColumnMapping, strategy: 'skip' | 'merge') =>
    api<ImportSummary>('/api/admin/leads/import', { method: 'POST', body: JSON.stringify({ rows, mapping, strategy }) }),
  sheet: (url: string) =>
    api<{ rows: RawRow[]; headers: string[] }>('/api/admin/leads/import/sheet', {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),
};

/** Live-chat visitor details shown next to a web conversation. */
export type VisitorInfo = {
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
  online: boolean;
  typing: boolean;
  last_seen_at: string;
  created_at: string;
};

export type SendBody = {
  text?: string;
  subject?: string;
  template?: { name: string; language: string; params?: string[] };
};

export const inboxApi = {
  conversations: () => api<{ conversations: Conversation[]; channels: ChannelStatus }>('/api/admin/inbox'),
  thread: (key: string, markRead = true) =>
    api<{ messages: Message[]; lead: Lead | null; visitor: VisitorInfo | null }>(
      `/api/admin/inbox/thread?key=${encodeURIComponent(key)}${markRead ? '' : '&read=0'}`,
    ),
  send: (key: string, body: SendBody) =>
    api<{ message: Message }>('/api/admin/inbox/send', { method: 'POST', body: JSON.stringify({ key, ...body }) }).then((d) => d.message),
  typing: (key: string) => api<{ ok: boolean }>('/api/admin/inbox/typing', { method: 'POST', body: JSON.stringify({ key }) }),
};

export const pushApi = {
  info: () => api<{ configured: boolean; publicKey: string }>('/api/admin/push'),
  subscribe: (subscription: PushSubscriptionJSON) =>
    api<{ ok: boolean }>('/api/admin/push', { method: 'POST', body: JSON.stringify(subscription) }),
  unsubscribe: (endpoint: string) =>
    api<{ ok: boolean }>('/api/admin/push', { method: 'DELETE', body: JSON.stringify({ endpoint }) }),
  test: () => api<{ push: number; telegram: boolean }>('/api/admin/push/test', { method: 'POST' }),
};

/** Downloads text as a file in the browser. */
export function downloadText(text: string, filename: string, type = 'text/csv;charset=utf-8') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
