import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";

import { SESSION_COOKIE, sessionSecret, verifySessionCookie } from "@/lib/session";

import SiteNav from "./SiteNav";
import { THEME_BOOT_SCRIPT } from "./ThemeToggle";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "MTK RADAR AI",
    template: "%s — MTK RADAR AI",
  },
  description:
    "Trusted offer discovery, real claim walkthroughs, and scheduled multi-platform publishing.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0b0d12" },
    { media: "(prefers-color-scheme: light)", color: "#f7f8fb" },
  ],
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const secret = sessionSecret();
  const store = await cookies();
  const session = secret
    ? await verifySessionCookie(store.get(SESSION_COOKIE)?.value, secret)
    : null;

  return (
    // The boot script sets data-theme before hydration, so React must not
    // treat that attribute as a mismatch.
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT_SCRIPT }} />
      </head>
      <body>
        <a href="#main-content" className="skip-link">Skip to content</a>
        {session ? (
          <div className="app-shell">
            <SiteNav actor={session.actor} />
            <div className="app-main" id="main-content">{children}</div>
          </div>
        ) : (
          <div id="main-content">{children}</div>
        )}
      </body>
    </html>
  );
}
