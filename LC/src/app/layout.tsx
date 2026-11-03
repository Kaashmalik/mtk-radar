import type { Metadata, Viewport } from "next";
import { Fraunces, Manrope } from "next/font/google";
import { Toaster } from "sonner";
import { brand } from "@/lib/config";
import { JsonLd, organizationLd, websiteLd } from "@/lib/seo";
import { ConsentAndAds } from "@/components/site/consent";
import "./globals.css";

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  axes: ["SOFT", "opsz"],
  style: ["normal", "italic"],
});

const manrope = Manrope({
  variable: "--font-manrope",
  subsets: ["latin"],
});

const title = "Laraib Creative — Ladies Suit Stitching in Lahore with Doorstep Pickup";
const description =
  "Premium ladies tailoring in Lahore: our riders collect your fabric, master tailors stitch to your saved measurements, and you track every step. Simple, designer, party, maxi & bridal suits.";

export const metadata: Metadata = {
  metadataBase: new URL(`https://${brand.domain}`),
  title: { default: title, template: "%s · Laraib Creative" },
  description,
  applicationName: brand.name,
  keywords: [
    "ladies tailor Lahore",
    "online suit stitching Lahore",
    "ladies suit stitching",
    "stitching service with pickup",
    "darzi Lahore",
    "silai Lahore",
    "party wear stitching Lahore",
    "bridal stitching Lahore",
    "Garhi Shahu tailor",
  ],
  authors: [{ name: brand.name, url: `https://${brand.domain}` }],
  creator: brand.name,
  publisher: brand.name,
  category: "Fashion & tailoring",
  alternates: { canonical: "./" },
  formatDetection: { telephone: true, address: true, email: true },
  openGraph: {
    type: "website",
    siteName: brand.name,
    locale: "en_PK",
    url: "./",
    title,
    description,
  },
  twitter: { card: "summary_large_image", title, description },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-image-preview": "large", "max-snippet": -1, "max-video-preview": -1 },
  },
  // SVG for modern browsers; PNGs in multiples of 48px for Google's search-result favicon
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/brand-icon/48.png", sizes: "48x48", type: "image/png" },
      { url: "/brand-icon/96.png", sizes: "96x96", type: "image/png" },
      { url: "/brand-icon/192.png", sizes: "192x192", type: "image/png" },
    ],
    apple: [{ url: "/apple-icon", sizes: "180x180", type: "image/png" }],
  },
  verification: {
    google: process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION,
    other: process.env.NEXT_PUBLIC_BING_SITE_VERIFICATION ? { "msvalidate.01": process.env.NEXT_PUBLIC_BING_SITE_VERIFICATION } : undefined,
  },
  other: process.env.NEXT_PUBLIC_ADSENSE_CLIENT ? { "google-adsense-account": process.env.NEXT_PUBLIC_ADSENSE_CLIENT } : undefined,
  appleWebApp: { capable: true, title: "Laraib", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  themeColor: "#3b1f2b",
  colorScheme: "light",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-PK" className={`${fraunces.variable} ${manrope.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[100] focus:rounded-full focus:bg-plum focus:px-4 focus:py-2 focus:text-ivory">
          Skip to content
        </a>
        <JsonLd data={[organizationLd, websiteLd]} />
        {children}
        <ConsentAndAds />
        <Toaster position="top-center" toastOptions={{ style: { fontFamily: "var(--font-sans)" } }} />
      </body>
    </html>
  );
}
