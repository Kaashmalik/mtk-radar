import { NextResponse } from 'next/server';
import {
  ADMIN_COOKIE,
  adminConfigured,
  adminEmail,
  checkCredentials,
  clearLoginAttempts,
  createSessionToken,
  loginThrottled,
  sessionCookieOptions,
} from '@/lib/admin-auth';
import { clientIp } from '@/lib/rate-limit';

export const dynamic = 'force-dynamic';

export async function POST(req: Request) {
  if (!adminConfigured()) {
    return NextResponse.json(
      {
        error:
          'Admin login is not configured. Set ADMIN_EMAIL, ADMIN_PASSWORD and ADMIN_SESSION_SECRET in your environment.',
      },
      { status: 503 },
    );
  }

  const ip = clientIp(req);

  if (await loginThrottled(ip)) {
    return NextResponse.json({ error: 'Too many attempts. Try again in a few minutes.' }, { status: 429 });
  }

  let body: { email?: unknown; password?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'Invalid request.' }, { status: 400 });
  }

  const email = typeof body.email === 'string' ? body.email : '';
  const password = typeof body.password === 'string' ? body.password : '';

  if (!checkCredentials(email, password)) {
    return NextResponse.json({ error: 'Incorrect email or password.' }, { status: 401 });
  }

  await clearLoginAttempts(ip);
  const res = NextResponse.json({ ok: true, email: adminEmail() });
  res.cookies.set(ADMIN_COOKIE, createSessionToken(adminEmail()), sessionCookieOptions());
  return res;
}
