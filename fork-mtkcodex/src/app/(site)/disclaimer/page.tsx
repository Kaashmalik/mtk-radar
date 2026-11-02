import type { Metadata } from 'next';
import { pageMeta } from '@/lib/seo';
import { site } from '@/data/site';
import LegalPage from '@/components/ui/LegalPage';

export const metadata: Metadata = pageMeta({
  title: 'Disclaimer',
  description: `General information, results and advertising disclaimer for the ${site.name} website.`,
  path: '/disclaimer',
});

export default function DisclaimerPage() {
  return (
    <LegalPage current="/disclaimer" title="Disclaimer" intro={`The information on ${site.url} is provided in good faith for general information about our company, products and services.`}>
      <h2>General information</h2>
      <p>Articles and guides are for educational purposes and are not legal, financial or professional advice for your specific situation.</p>

      <h2>Product demos and sample data</h2>
      <p>
        Interactive previews, dashboards, CRM boards, scraping logs and charts on this site use sample data to illustrate how our software works. Figures
        labelled as statistics about MTK Codex (such as products shipped or uptime) describe our own platforms.
      </p>

      <h2>Results</h2>
      <p>Client testimonials reflect individual experiences. Outcomes depend on each business, its data and its processes, and are not guaranteed.</p>

      <h2>External links and advertising</h2>
      <p>We may link to third-party websites or display third-party ads. We do not endorse and are not responsible for their content.</p>
    </LegalPage>
  );
}
