import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";

import { SESSION_COOKIE, sessionSecret, verifySessionCookie } from "@/lib/session";

import SiteNav from "./SiteNav";

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
    { media: "(prefers-color-scheme: dark)", color: "#0d1117" },
    { media: "(prefers-color-scheme: light)", color: "#f6f8fa" },
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
    <html lang="en">
      <body>
        {session ? <SiteNav actor={session.actor} /> : null}
        {children}
      </body>
    </html>
  );
}
