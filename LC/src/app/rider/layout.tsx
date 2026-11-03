import type { Metadata, Viewport } from "next";

export const metadata: Metadata = { title: "Rider", robots: { index: false } };
export const viewport: Viewport = { themeColor: "#3b1f2b", width: "device-width", initialScale: 1 };

export default function RiderLayout({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen bg-[#f4efe7]">{children}</div>;
}
