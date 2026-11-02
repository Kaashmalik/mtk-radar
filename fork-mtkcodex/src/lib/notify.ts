import webpush from 'web-push';
import { mutateTable, readTable } from '@/lib/file-store';
import { supabase } from '@/lib/supabase';
import { storageMode } from '@/lib/leads';

/**
 * Owner alerts for new chats, replies and enquiries, wherever you are:
 *  - Web Push to the installed admin app (phone or desktop), free.
 *    Env: VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT (mailto:you@…)
 *  - Telegram bot message, free and very reliable on mobile.
 *    Env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
 * Alerts never throw: a failed alert must not break the request that caused it.
 */

const env = (key: string) => (process.env[key] || '').trim();

export function pushConfigured(): boolean {
  return Boolean(env('VAPID_PUBLIC_KEY') && env('VAPID_PRIVATE_KEY'));
}

export function vapidPublicKey(): string {
  return env('VAPID_PUBLIC_KEY');
}

export function telegramConfigured(): boolean {
  return Boolean(env('TELEGRAM_BOT_TOKEN') && env('TELEGRAM_CHAT_ID'));
}

export type PushSubscriptionRow = { endpoint: string; p256dh: string; auth: string; user_agent: string; created_at?: string };

export async function savePushSubscription(row: PushSubscriptionRow): Promise<void> {
  if (storageMode() === 'supabase') {
    await supabase('push_subscriptions?on_conflict=endpoint', {
      method: 'POST',
      headers: { Prefer: 'resolution=merge-duplicates,return=minimal' },
      body: JSON.stringify(row),
    });
    return;
  }
  await mutateTable<PushSubscriptionRow, void>('push', (rows) => {
    const index = rows.findIndex((r) => r.endpoint === row.endpoint);
    if (index >= 0) rows[index] = row;
    else rows.push({ ...row, created_at: new Date().toISOString() });
  });
}

export async function removePushSubscription(endpoint: string): Promise<void> {
  if (storageMode() === 'supabase') {
    await supabase(`push_subscriptions?endpoint=eq.${encodeURIComponent(endpoint)}`, { method: 'DELETE' });
    return;
  }
  await mutateTable<PushSubscriptionRow, void>('push', (rows) => {
    const kept = rows.filter((r) => r.endpoint !== endpoint);
    rows.splice(0, rows.length, ...kept);
  });
}

async function listPushSubscriptions(): Promise<PushSubscriptionRow[]> {
  if (storageMode() === 'supabase') return supabase<PushSubscriptionRow[]>('push_subscriptions?select=*');
  if (storageMode() === 'file') return readTable<PushSubscriptionRow>('push');
  return [];
}

export type Alert = { title: string; body: string; url: string; tag?: string };

async function sendPush(alert: Alert): Promise<number> {
  if (!pushConfigured()) return 0;
  webpush.setVapidDetails(env('VAPID_SUBJECT') || 'mailto:admin@mtkcodex.tech', env('VAPID_PUBLIC_KEY'), env('VAPID_PRIVATE_KEY'));
  const subscriptions = await listPushSubscriptions();
  let sent = 0;
  await Promise.all(
    subscriptions.map(async (sub) => {
      try {
        await webpush.sendNotification(
          { endpoint: sub.endpoint, keys: { p256dh: sub.p256dh, auth: sub.auth } },
          JSON.stringify(alert),
          { TTL: 60 * 60, urgency: 'high' },
        );
        sent++;
      } catch (error) {
        const status = (error as { statusCode?: number }).statusCode;
        // 404/410: the browser dropped this subscription; forget it.
        if (status === 404 || status === 410) await removePushSubscription(sub.endpoint).catch(() => undefined);
        else console.error('notify: push failed', status, error instanceof Error ? error.message : error);
      }
    }),
  );
  return sent;
}

async function sendTelegram(alert: Alert): Promise<boolean> {
  if (!telegramConfigured()) return false;
  const base = (process.env.NEXT_PUBLIC_SITE_URL || 'https://mtkcodex.tech').replace(/\/+$/, '');
  const res = await fetch(`https://api.telegram.org/bot${env('TELEGRAM_BOT_TOKEN')}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chat_id: env('TELEGRAM_CHAT_ID'),
      text: `${alert.title}\n${alert.body}\n${base}${alert.url}`,
      disable_web_page_preview: true,
    }),
    signal: AbortSignal.timeout(8000),
  });
  return res.ok;
}

/** Sends an alert on every configured channel. Returns how many went out. */
export async function notifyOwner(alert: Alert): Promise<{ push: number; telegram: boolean }> {
  const trimmed = { ...alert, title: alert.title.slice(0, 80), body: alert.body.slice(0, 240) };
  const [push, telegram] = await Promise.all([
    sendPush(trimmed).catch((error) => {
      console.error('notify: push error', error instanceof Error ? error.message : error);
      return 0;
    }),
    sendTelegram(trimmed).catch((error) => {
      console.error('notify: telegram error', error instanceof Error ? error.message : error);
      return false;
    }),
  ]);
  return { push, telegram };
}

/* ---------------------------------------------------------------------------
 * Admin presence: "the team is online" in the chat widget
 * ------------------------------------------------------------------------- */

type StateRow = { key: string; value: Record<string, unknown>; updated_at: string };
const PRESENCE_KEY = 'admin_presence';
const ONLINE_MS = 2 * 60 * 1000;
let lastPresenceWrite = 0;
let presenceCache: { at: number; online: boolean } | null = null;

/** Called while the inbox is open. Throttled to one write per 30 s per instance. */
export async function markAdminActive(): Promise<void> {
  const now = Date.now();
  // This instance knows right away; others see it within their 15 s cache.
  presenceCache = { at: now, online: true };
  if (now - lastPresenceWrite < 30_000 || storageMode() === 'readonly') return;
  lastPresenceWrite = now;
  const row: StateRow = { key: PRESENCE_KEY, value: {}, updated_at: new Date(now).toISOString() };
  try {
    if (storageMode() === 'supabase') {
      await supabase('app_state?on_conflict=key', {
        method: 'POST',
        headers: { Prefer: 'resolution=merge-duplicates,return=minimal' },
        body: JSON.stringify(row),
      });
      return;
    }
    await mutateTable<StateRow, void>('state', (rows) => {
      const index = rows.findIndex((r) => r.key === PRESENCE_KEY);
      if (index >= 0) rows[index] = row;
      else rows.push(row);
    });
  } catch {
    // Presence is cosmetic.
  }
}

/** Whether the owner had the inbox open in the last two minutes (cached 15 s). */
export async function adminOnline(): Promise<boolean> {
  if (presenceCache && Date.now() - presenceCache.at < 15_000) return presenceCache.online;
  let updated = '';
  try {
    if (storageMode() === 'supabase') {
      const rows = await supabase<StateRow[]>(`app_state?key=eq.${PRESENCE_KEY}&select=updated_at`);
      updated = rows[0]?.updated_at || '';
    } else if (storageMode() === 'file') {
      updated = (await readTable<StateRow>('state')).find((r) => r.key === PRESENCE_KEY)?.updated_at || '';
    }
  } catch {
    updated = '';
  }
  const online = Boolean(updated) && Date.now() - new Date(updated).getTime() < ONLINE_MS;
  presenceCache = { at: Date.now(), online };
  return online;
}
