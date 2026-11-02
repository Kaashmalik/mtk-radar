'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { Eye, EyeOff, Loader2, LockKeyhole } from 'lucide-react';

export default function LoginForm({ email }: { email: string }) {
  const router = useRouter();
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setBusy(true);
    try {
      const res = await fetch('/api/admin/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const data = (await res.json().catch(() => ({}))) as { error?: string };
      if (!res.ok) {
        setError(data.error || 'Sign in failed.');
        setBusy(false);
        return;
      }
      router.replace('/admin');
      router.refresh();
    } catch {
      setError('Network error. Please try again.');
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-6 space-y-4">
      <div>
        <label htmlFor="admin-email" className="mb-1.5 block text-sm font-medium">
          Email
        </label>
        <input
          id="admin-email"
          type="email"
          value={email}
          readOnly
          autoComplete="username"
          className="h-11 w-full rounded-xl border border-line bg-muted/50 px-3 text-sm text-fg-muted"
        />
      </div>

      <div>
        <label htmlFor="admin-password" className="mb-1.5 block text-sm font-medium">
          Password
        </label>
        <div className="relative">
          <input
            id="admin-password"
            type={show ? 'text' : 'password'}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
            autoFocus
            className="h-11 w-full rounded-xl border border-line bg-elevated px-3 pr-11 text-sm outline-none transition focus:border-brand"
            placeholder="Enter your admin password"
          />
          <button
            type="button"
            onClick={() => setShow((value) => !value)}
            className="absolute inset-y-0 right-0 grid w-11 place-items-center text-fg-subtle hover:text-fg"
            aria-label={show ? 'Hide password' : 'Show password'}
          >
            {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
          </button>
        </div>
      </div>

      {error && (
        <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-500">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={busy}
        className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-full bg-cta font-semibold text-on-cta transition hover:bg-cta-hover disabled:opacity-60"
      >
        {busy ? <Loader2 className="size-4 animate-spin" /> : <LockKeyhole className="size-4" />}
        {busy ? 'Signing in…' : 'Sign in'}
      </button>
      <p className="text-center text-xs text-fg-subtle">Sessions expire after 8 hours.</p>
    </form>
  );
}
