import type { Metadata } from 'next';
import Link from 'next/link';
import { redirect } from 'next/navigation';
import { getAdminSession } from '@/lib/admin-auth';
import { storageMode } from '@/lib/leads';
import { supabase } from '@/lib/supabase';
import { Logo } from '@/components/ui/primitives';
import LogoutButton from '@/components/admin/LogoutButton';

export const metadata: Metadata = {
  title: 'Admin',
  robots: { index: false, follow: false },
  manifest: '/admin/manifest.webmanifest',
  appleWebApp: { capable: true, title: 'MTK CRM', statusBarStyle: 'black-translucent' },
};

export const dynamic = 'force-dynamic';

/** Unread messages (WhatsApp, email and live chat) for the nav badge. Never blocks the page. */
async function unreadCount(): Promise<number> {
  if (storageMode() !== 'supabase') return 0;
  try {
    const [leads, chats] = await Promise.all([
      supabase<{ unread_count: number }[]>('leads?unread_count=gt.0&select=unread_count&limit=1000'),
      supabase<{ unread_admin: number }[]>('chat_sessions?unread_admin=gt.0&select=unread_admin&limit=1000'),
    ]);
    return leads.reduce((sum, row) => sum + row.unread_count, 0) + chats.reduce((sum, row) => sum + row.unread_admin, 0);
  } catch {
    return 0;
  }
}

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const session = await getAdminSession();
  if (!session) redirect('/admin/login');

  const unread = await unreadCount();
  const nav = [
    { href: '/admin', label: 'Leads' },
    { href: '/admin/inbox', label: 'Inbox', badge: unread },
    { href: '/admin/deals', label: 'Deals' },
    { href: '/admin/outreach', label: 'Outreach' },
    { href: '/admin/analytics', label: 'Analytics' },
    { href: '/admin/docs', label: 'Playbook' },
    { href: '/admin/settings', label: 'Settings' },
  ];

  return (
    <div className="min-h-dvh bg-bg">
      <header className="sticky top-0 z-40 border-b border-line bg-elevated/90 backdrop-blur">
        <div className="container-x flex h-16 items-center justify-between gap-4">
          <div className="flex items-center gap-6">
            <Link href="/admin" aria-label="MTK Codex admin home">
              <Logo />
            </Link>
            <nav className="hidden items-center gap-1 md:flex">
              {nav.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-fg-muted transition hover:bg-muted hover:text-fg"
                >
                  {item.label}
                  {item.badge ? <span className="rounded-full bg-cta px-1.5 text-[10px] font-bold text-on-cta">{item.badge}</span> : null}
                </Link>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden text-xs text-fg-subtle lg:inline">{session.email}</span>
            <LogoutButton />
          </div>
        </div>
        <nav className="container-x flex items-center gap-1 overflow-x-auto pb-2 md:hidden">
          {nav.map((item) => (
            <Link key={item.href} href={item.href} className="inline-flex shrink-0 items-center gap-1 rounded-lg px-3 py-1.5 text-sm text-fg-muted hover:text-fg">
              {item.label}
              {item.badge ? <span className="rounded-full bg-cta px-1.5 text-[10px] font-bold text-on-cta">{item.badge}</span> : null}
            </Link>
          ))}
        </nav>
      </header>
      <main className="container-x py-8">{children}</main>
    </div>
  );
}
