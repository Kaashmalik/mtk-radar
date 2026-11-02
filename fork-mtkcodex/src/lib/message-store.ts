import { randomUUID } from 'node:crypto';
import { mutateTable, readTable } from '@/lib/file-store';
import { storageMode } from '@/lib/leads';
import { supabase } from '@/lib/supabase';
import type { Message } from '@/lib/lead-types';

/** Message storage shared by the inbox and the live chat. */

export type NewMessage = Omit<Message, 'id' | 'created_at' | 'meta' | 'subject' | 'sender' | 'error'> &
  Partial<Pick<Message, 'meta' | 'subject' | 'sender' | 'error' | 'created_at'>>;

/** Inserts a message; returns null when external_id was already stored (webhook retry). */
export async function insertMessage(message: NewMessage): Promise<Message | null> {
  const row = { subject: '', sender: '', error: '', meta: {}, ...message };
  if (storageMode() === 'supabase') {
    const rows = await supabase<Message[]>('messages?on_conflict=external_id&select=*', {
      method: 'POST',
      headers: { Prefer: 'resolution=ignore-duplicates,return=representation' },
      body: JSON.stringify(row),
    });
    return rows[0] || null;
  }
  return mutateTable<Message, Message | null>('messages', (rows) => {
    if (row.external_id && rows.some((r) => r.external_id === row.external_id)) return null;
    const created: Message = { id: randomUUID(), created_at: new Date().toISOString(), ...row } as Message;
    rows.push(created);
    return created;
  });
}

/** Links every message in a thread to a lead (after a visitor identifies themselves). */
export async function linkThreadToLead(threadKey: string, leadId: string): Promise<void> {
  if (storageMode() === 'supabase') {
    await supabase(`messages?thread_key=eq.${encodeURIComponent(threadKey)}&lead_id=is.null`, {
      method: 'PATCH',
      body: JSON.stringify({ lead_id: leadId }),
    });
    return;
  }
  await mutateTable<Message, void>('messages', (rows) => {
    for (const row of rows) if (row.thread_key === threadKey && !row.lead_id) row.lead_id = leadId;
  });
}

export async function listThread(threadKey: string, options: { after?: string; limit?: number } = {}): Promise<Message[]> {
  const limit = options.limit ?? 300;
  if (storageMode() === 'readonly') return [];
  if (storageMode() === 'supabase') {
    const after = options.after ? `&created_at=gt.${encodeURIComponent(options.after)}` : '';
    const rows = await supabase<Message[]>(
      `messages?thread_key=eq.${encodeURIComponent(threadKey)}${after}&select=*&order=created_at.desc&limit=${limit}`,
    );
    return rows.reverse();
  }
  const rows = await readTable<Message>('messages');
  return rows
    .filter((row) => row.thread_key === threadKey && (!options.after || row.created_at > options.after))
    .sort((a, b) => a.created_at.localeCompare(b.created_at))
    .slice(-limit);
}
