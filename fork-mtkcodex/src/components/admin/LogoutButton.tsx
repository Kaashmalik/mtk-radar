'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { LogOut } from 'lucide-react';

export default function LogoutButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function logout() {
    setBusy(true);
    await fetch('/api/admin/logout', { method: 'POST' }).catch(() => {});
    router.replace('/admin/login');
    router.refresh();
  }

  return (
    <button
      type="button"
      onClick={logout}
      disabled={busy}
      className="inline-flex h-9 items-center gap-1.5 rounded-full border border-line px-3 text-xs font-semibold text-fg-muted transition hover:border-brand hover:text-brand disabled:opacity-50"
    >
      <LogOut className="size-3.5" aria-hidden />
      {busy ? 'Signing out…' : 'Sign out'}
    </button>
  );
}
