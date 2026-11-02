import AnnouncementBar from '@/components/layout/AnnouncementBar';
import Navbar from '@/components/layout/Navbar';
import Footer from '@/components/layout/Footer';
import FloatingContact from '@/components/layout/FloatingContact';
import { ScrollProgress, SpotlightProvider } from '@/components/motion/Effects';
import CookieConsent from '@/components/layout/CookieConsent';
import MtkBot from '@/components/bot/MtkBot';
import ThirdPartyScripts from '@/components/layout/ThirdPartyScripts';
import AnalyticsBeacon from '@/components/analytics/AnalyticsBeacon';

// Public marketing site chrome. The admin area deliberately lives outside this
// route group so it renders without the navbar, footer, chat bot and consent UI.
export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-lg focus:bg-cta focus:px-4 focus:py-2 focus:text-on-cta"
      >
        Skip to content
      </a>
      <ScrollProgress />
      <SpotlightProvider />
      <AnnouncementBar />
      <Navbar />
      <main id="main">{children}</main>
      <Footer />
      <FloatingContact />
      <MtkBot />
      <CookieConsent />
      <ThirdPartyScripts />
      <AnalyticsBeacon />
    </>
  );
}
