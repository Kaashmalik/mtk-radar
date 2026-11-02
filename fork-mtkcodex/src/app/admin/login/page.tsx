import type { Metadata } from 'next';
import { redirect } from 'next/navigation';
import { adminConfigured, adminEmail, getAdminSession } from '@/lib/admin-auth';
import { Logo } from '@/components/ui/primitives';
import LoginForm from '@/components/admin/LoginForm';

export const metadata: Metadata = {
  title: 'Admin sign in',
  robots: { index: false, follow: false },
};

export const dynamic = 'force-dynamic';

export default async function AdminLoginPage() {
  if (await getAdminSession()) redirect('/admin');

  const configured = adminConfigured();

  return (
    <div className="grid min-h-dvh place-items-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-8 flex justify-center">
          <Logo />
        </div>
        <div className="card p-6 sm:p-8">
          <p className="eyebrow">MTK Codex</p>
          <h1 className="mt-3 text-2xl font-bold">Admin sign in</h1>
          <p className="mt-2 text-sm leading-relaxed text-fg-muted">
            Lead CRM and outreach desk. Access is limited to the business owner.
          </p>

          {configured ? (
            <LoginForm email={adminEmail()} />
          ) : (
            <div className="mt-6 rounded-xl border border-line bg-muted/60 p-4 text-sm leading-relaxed text-fg-muted">
              <p className="font-semibold text-fg">Admin login is not configured yet.</p>
              <p className="mt-2">
                Add <code className="rounded bg-elevated px-1">ADMIN_EMAIL</code>,{' '}
                <code className="rounded bg-elevated px-1">ADMIN_PASSWORD</code> and{' '}
                <code className="rounded bg-elevated px-1">ADMIN_SESSION_SECRET</code> to your environment,
                then reload this page.
              </p>
            </div>
          )}
        </div>
        <p className="mt-6 text-center text-xs text-fg-subtle">
          Trouble signing in? Email {adminEmail()}.
        </p>
      </div>
    </div>
  );
}
