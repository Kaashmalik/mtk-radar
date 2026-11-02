import { NextResponse } from 'next/server';
import { ADMIN_COOKIE, sessionCookieOptions } from '@/lib/admin-auth';

export const dynamic = 'force-dynamic';

export async function POST() {
  const res = NextResponse.json({ ok: true });
  res.cookies.set(ADMIN_COOKIE, '', { ...sessionCookieOptions(), maxAge: 0 });
  return res;
}
