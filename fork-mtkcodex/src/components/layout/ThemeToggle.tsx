'use client';

import { Moon, Sun } from 'lucide-react';

const THEME_COLORS = { dark: '#031f2b', light: '#f5f8f7' } as const;

/** Keeps the mobile browser chrome in sync with the chosen theme. */
function syncThemeColor(isDark: boolean) {
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (meta) meta.content = isDark ? THEME_COLORS.dark : THEME_COLORS.light;
}

export default function ThemeToggle() {
  const toggle = () => {
    const isDark = document.documentElement.classList.toggle('dark');
    syncThemeColor(isDark);
    try {
      localStorage.setItem('theme', isDark ? 'dark' : 'light');
    } catch {}
  };

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label="Toggle dark mode"
      className="grid size-10 place-items-center rounded-full border border-line text-fg-muted transition hover:border-brand hover:text-brand"
    >
      <Sun className="hidden size-[18px] dark:block" />
      <Moon className="size-[18px] dark:hidden" />
    </button>
  );
}
