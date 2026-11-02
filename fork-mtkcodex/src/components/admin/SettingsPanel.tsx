'use client';

import { useEffect, useState } from 'react';
import { Bell, BellOff, CheckCircle2, Copy, Smartphone, XCircle } from 'lucide-react';
import { pushApi } from '@/components/admin/client-api';
import { Toast, buttonClass, primaryButtonClass, useNotice } from '@/components/admin/ui';

export type ChannelRow = { name: string; on: boolean; what: string; missing: string[] };

function base64ToUint8(base64: string): Uint8Array<ArrayBuffer> {
  const padded = (base64 + '='.repeat((4 - (base64.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

type PushState = 'unsupported' | 'unconfigured' | 'off' | 'on' | 'denied' | 'loading';

export default function SettingsPanel({ channels, webhooks }: { channels: ChannelRow[]; webhooks: { label: string; url: string }[] }) {
  const [push, setPush] = useState<PushState>('loading');
  const [busy, setBusy] = useState(false);
  const { toast, setToast, error, fail } = useNotice();

  useEffect(() => {
    (async () => {
      if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) return setPush('unsupported');
      const info = await pushApi.info().catch(() => null);
      if (!info?.configured) return setPush('unconfigured');
      if (Notification.permission === 'denied') return setPush('denied');
      const registration = await navigator.serviceWorker.getRegistration('/admin/');
      const subscription = await registration?.pushManager.getSubscription();
      setPush(subscription ? 'on' : 'off');
    })().catch(() => setPush('unsupported'));
  }, []);

  async function enable() {
    setBusy(true);
    try {
      const info = await pushApi.info();
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        setPush(permission === 'denied' ? 'denied' : 'off');
        return;
      }
      const registration = await navigator.serviceWorker.register('/admin/sw.js', { scope: '/admin/' });
      await navigator.serviceWorker.ready;
      const subscription =
        (await registration.pushManager.getSubscription()) ||
        (await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: base64ToUint8(info.publicKey) }));
      await pushApi.subscribe(subscription.toJSON());
      setPush('on');
      setToast('Alerts are on for this device');
    } catch (err) {
      fail(err, 'Could not turn on alerts');
    } finally {
      setBusy(false);
    }
  }

  async function disable() {
    setBusy(true);
    try {
      const registration = await navigator.serviceWorker.getRegistration('/admin/');
      const subscription = await registration?.pushManager.getSubscription();
      if (subscription) {
        await pushApi.unsubscribe(subscription.endpoint);
        await subscription.unsubscribe();
      }
      setPush('off');
      setToast('Alerts off for this device');
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function test() {
    setBusy(true);
    try {
      const result = await pushApi.test();
      setToast(`Test sent: ${result.push} device(s)${result.telegram ? ' + Telegram' : ''}`);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setToast('Copied');
    } catch {
      fail(new Error('Copy failed — select the text manually.'));
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <p className="eyebrow">Settings</p>
      <h1 className="mt-2 text-3xl font-bold">Channels &amp; alerts</h1>
      <p className="mt-1 text-sm text-fg-muted">
        Everything is optional and free to start. Step-by-step setup lives in <code>docs/CRM.md</code> → “Go-live checklist”.
      </p>

      <section className="card mt-6 p-5">
        <h2 className="flex items-center gap-2 font-bold">
          <Bell className="size-4 text-brand" /> Alerts on this device
        </h2>
        <p className="mt-1 text-sm text-fg-muted">
          Get a notification for every new chat, WhatsApp reply, email and enquiry — on your phone or laptop.
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          {push === 'on' ? (
            <>
              <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-emerald-600">
                <CheckCircle2 className="size-4" /> On for this device
              </span>
              <button onClick={test} disabled={busy} className={buttonClass}>
                Send test alert
              </button>
              <button onClick={disable} disabled={busy} className={buttonClass}>
                <BellOff className="size-4" /> Turn off
              </button>
            </>
          ) : push === 'off' ? (
            <button onClick={enable} disabled={busy} className={primaryButtonClass}>
              <Bell className="size-4" /> Turn on alerts
            </button>
          ) : (
            <p className="text-sm text-fg-muted">
              {push === 'loading' && 'Checking…'}
              {push === 'unsupported' && 'This browser does not support push alerts. On iPhone, install the app first (below), then open it from the home screen.'}
              {push === 'unconfigured' && 'Push is not configured yet: add VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY (see the checklist).'}
              {push === 'denied' && 'Notifications are blocked for this site. Allow them in the browser settings, then reload.'}
            </p>
          )}
          {push !== 'on' && push !== 'loading' && (
            <button onClick={test} disabled={busy} className={buttonClass}>
              Test Telegram / other devices
            </button>
          )}
        </div>
        {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
      </section>

      <section className="card mt-4 p-5">
        <h2 className="flex items-center gap-2 font-bold">
          <Smartphone className="size-4 text-brand" /> Install on your phone
        </h2>
        <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-sm text-fg-muted">
          <li>Open <code>/admin/inbox</code> on your phone and sign in.</li>
          <li>
            <strong>Android (Chrome):</strong> menu ⋮ → <em>Install app</em>. <strong>iPhone (Safari):</strong> Share →{' '}
            <em>Add to Home Screen</em>.
          </li>
          <li>Open “MTK CRM” from the home screen, go to Settings, and tap <em>Turn on alerts</em>.</li>
        </ol>
      </section>

      <section className="card mt-4 overflow-hidden">
        <h2 className="px-5 pt-5 font-bold">Channels</h2>
        <ul className="mt-3 divide-y divide-line">
          {channels.map((row) => (
            <li key={row.name} className="flex items-start gap-3 px-5 py-3 text-sm">
              {row.on ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-500" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-fg-subtle" />}
              <div className="min-w-0 flex-1">
                <p className="font-semibold">{row.name}</p>
                <p className="text-xs text-fg-muted">{row.what}</p>
                {!row.on && row.missing.length > 0 && (
                  <p className="mt-1 text-[11px] text-amber-600">
                    Missing: {row.missing.map((name) => <code key={name} className="mr-1 rounded bg-muted px-1">{name}</code>)}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="card mt-4 p-5">
        <h2 className="font-bold">Webhook URLs</h2>
        <p className="mt-1 text-sm text-fg-muted">Paste these into Resend and Meta when you connect each channel.</p>
        <ul className="mt-3 space-y-2">
          {webhooks.map((hook) => (
            <li key={hook.url} className="flex flex-wrap items-center gap-2 text-sm">
              <span className="w-40 shrink-0 font-semibold">{hook.label}</span>
              <code className="min-w-0 flex-1 truncate rounded-lg bg-muted px-2 py-1 text-xs">{hook.url}</code>
              <button onClick={() => copy(hook.url)} className="inline-flex items-center gap-1 text-xs font-semibold text-brand" aria-label={`Copy ${hook.label}`}>
                <Copy className="size-3.5" /> Copy
              </button>
            </li>
          ))}
        </ul>
      </section>
      <Toast message={toast} />
    </div>
  );
}
