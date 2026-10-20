import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MTK RADAR AI",
  description:
    "Trusted offer discovery, real claim walkthroughs, and scheduled multi-platform publishing.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
