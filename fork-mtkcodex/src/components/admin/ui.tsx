'use client';

import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Check, X } from 'lucide-react';

/** Toast + error state shared by every admin screen. */
export function useNotice() {
  const [toast, setToast] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(''), 3500);
    return () => clearTimeout(timer);
  }, [toast]);

  const fail = useCallback((err: unknown, fallback = 'Something went wrong') => {
    setError(err instanceof Error ? err.message : fallback);
  }, []);

  return { toast, setToast, error, setError, fail };
}

export function Toast({ message }: { message: string }) {
  if (!message) return null;
  return (
    <div
      role="status"
      className="fixed bottom-5 left-1/2 z-[70] flex -translate-x-1/2 items-center gap-2 rounded-full bg-fg px-4 py-2 text-sm font-semibold text-bg shadow-float"
    >
      <Check className="size-4" /> {message}
    </div>
  );
}

export function ErrorBanner({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="mt-4 flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-500"
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0" />
      <span className="min-w-0 break-words">{message}</span>
      <button onClick={onDismiss} className="ml-auto" aria-label="Dismiss error">
        <X className="size-4" />
      </button>
    </div>
  );
}

export function Notice({ children, tone = 'amber' }: { children: React.ReactNode; tone?: 'amber' | 'sky' }) {
  const tones = {
    amber: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400',
    sky: 'border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300',
  };
  return (
    <div className={`mt-3 flex items-start gap-2 rounded-xl border px-4 py-3 text-xs leading-relaxed ${tones[tone]}`}>
      <AlertTriangle className="mt-0.5 size-4 shrink-0" />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function StatCard({
  icon: Icon,
  label,
  value,
  hint,
  onClick,
  active,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: React.ReactNode;
  hint?: string;
  onClick?: () => void;
  active?: boolean;
}) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={`card flex items-center gap-3 p-4 text-left transition ${
        active ? 'border-brand ring-1 ring-brand/30' : onClick ? 'hover:border-brand/50' : ''
      }`}
    >
      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand">
        <Icon className="size-5" />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-2xl font-bold leading-tight">{value}</span>
        <span className="block truncate text-xs text-fg-subtle">{label}</span>
        {hint && <span className="block truncate text-[11px] text-fg-subtle/80">{hint}</span>}
      </span>
    </Tag>
  );
}

export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold text-fg-muted">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-fg-subtle">{hint}</span>}
    </label>
  );
}

export function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line bg-muted/40 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-fg-subtle">{label}</p>
      <p className="mt-0.5 truncate font-semibold capitalize">{value}</p>
    </div>
  );
}

export const inputClass =
  'h-10 w-full rounded-xl border border-line bg-elevated px-3 text-sm outline-none transition focus:border-brand';
export const textareaClass =
  'w-full rounded-xl border border-line bg-elevated px-3 py-2 text-sm leading-relaxed outline-none transition focus:border-brand';
export const buttonClass =
  'inline-flex h-10 items-center justify-center gap-2 rounded-full border border-line px-4 text-sm font-semibold text-fg-muted transition hover:border-brand hover:text-brand disabled:opacity-50';
export const primaryButtonClass =
  'inline-flex h-10 items-center justify-center gap-2 rounded-full bg-cta px-4 text-sm font-semibold text-on-cta transition hover:bg-cta-hover disabled:opacity-60';

/** Centered dialog with a backdrop; closes on Escape. */
export function Modal({
  title,
  onClose,
  children,
  wide,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center sm:items-center sm:p-4" role="dialog" aria-modal="true" aria-label={title}>
      <button className="absolute inset-0 bg-black/50" onClick={onClose} aria-label="Close dialog" />
      <div
        className={`relative flex max-h-[92dvh] w-full flex-col overflow-hidden rounded-t-2xl border border-line bg-elevated shadow-float sm:rounded-2xl ${
          wide ? 'sm:max-w-4xl' : 'sm:max-w-lg'
        }`}
      >
        <div className="flex items-center justify-between gap-4 border-b border-line px-5 py-4">
          <h2 className="text-lg font-bold">{title}</h2>
          <button onClick={onClose} className="rounded-lg border border-line p-2 text-fg-muted hover:text-fg" aria-label="Close">
            <X className="size-4" />
          </button>
        </div>
        <div className="overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}

/** Re-runs `fn` every `ms` while the tab is visible, and once when it becomes visible. */
export function usePolling(fn: () => void, ms: number, enabled = true) {
  useEffect(() => {
    if (!enabled) return;
    const tick = () => document.visibilityState === 'visible' && fn();
    const timer = window.setInterval(tick, ms);
    document.addEventListener('visibilitychange', tick);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', tick);
    };
  }, [fn, ms, enabled]);
}
