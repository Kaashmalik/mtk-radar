import type { Metadata, Viewport } from "next";

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

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <SiteNav />
        {children}
      </body>
    </html>
  );
}
