import { NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/admin-auth';
import { pushConfigured, removePushSubscription, savePushSubscription, vapidPublicKey } from '@/lib/notify';

export const dynamic = 'force-dynamic';

export async function GET(req: Request) {
  const session = await requireAdmin(req);
  if (session instanceof Response) return session;
  return NextResponse.json({ configured: pushConfigured(), publicKey: vapidPublicKey() });
}

/** Saves this device's push subscription (from PushManager.subscribe). */
export async function POST(req: Request) {
  const session = await requireAdmin(req);
  if (session instanceof Response) return session;
  if (!pushConfigured()) return NextResponse.json({ error: 'Push is not configured (VAPID keys).' }, { status: 503 });

  let body: { endpoint?: unknown; keys?: { p256dh?: unknown; auth?: unknown } };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }
  const endpoint = typeof body.endpoint === 'string' ? body.endpoint : '';
  const p256dh = typeof body.keys?.p256dh === 'string' ? body.keys.p256dh : '';
  const auth = typeof body.keys?.auth === 'string' ? body.keys.auth : '';
  if (!/^https:\/\//.test(endpoint) || endpoint.length > 1000 || !p256dh || !auth) {
    return NextResponse.json({ error: 'Invalid subscription' }, { status: 422 });
  }

  await savePushSubscription({ endpoint, p256dh, auth, user_agent: (req.headers.get('user-agent') || '').slice(0, 200) });
  return NextResponse.json({ ok: true });
}

export async function DELETE(req: Request) {
  const session = await requireAdmin(req);
  if (session instanceof Response) return session;
  let endpoint = '';
  try {
    endpoint = String(((await req.json()) as { endpoint?: unknown }).endpoint || '');
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }
  if (endpoint) await removePushSubscription(endpoint);
  return NextResponse.json({ ok: true });
}
