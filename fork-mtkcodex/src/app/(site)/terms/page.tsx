import type { Metadata } from 'next';
import { pageMeta } from '@/lib/seo';
import { site } from '@/data/site';
import LegalPage from '@/components/ui/LegalPage';

export const metadata: Metadata = pageMeta({
  title: 'Terms of Service',
  description: `Terms governing use of the ${site.name} website and engagement for our services.`,
  path: '/terms',
});

export default function TermsPage() {
  return (
    <LegalPage
      current="/terms"
      title="Terms of Service"
      intro={`These terms govern your use of ${site.url}. By using the website you agree to them. Paid engagements are governed by a separate written proposal or contract, which takes precedence if it conflicts with these terms.`}
    >
      <h2>1. Use of the website</h2>
      <p>You may browse and share this website for lawful purposes. You must not attempt to disrupt it, gain unauthorised access, or scrape it in a way that harms its availability.</p>

      <h2>2. Intellectual property</h2>
      <p>
        The website design, text, graphics, product names and logos belong to {site.name} unless stated otherwise. Product demos on this site are
        illustrative previews. For custom projects, ownership of delivered source code transfers to the client as set out in the project agreement.
      </p>

      <h2>3. Quotes and services</h2>
      <p>
        Prices shown on the website are indicative starting points. A project is confirmed only by a written proposal accepted by both parties, which defines
        scope, timeline, payment terms, warranties and support.
      </p>

      <h2>4. SaaS products</h2>
      <p>Subscriptions to MTK Codex platforms are subject to the plan terms provided at sign-up, including acceptable use, uptime commitments and data handling.</p>

      <h2>5. Data and scraping services</h2>
      <p>
        Clients are responsible for how they use data we deliver. We collect publicly available information only, respect site terms and robots.txt, and
        may decline projects that would breach law, third-party rights or privacy.
      </p>

      <h2>6. Third-party links and ads</h2>
      <p>The site may link to or display advertising from third parties. We are not responsible for their content, products or practices.</p>

      <h2>7. Disclaimer and liability</h2>
      <p>
        The website is provided &ldquo;as is&rdquo;. To the extent permitted by law, {site.name} is not liable for indirect or consequential losses arising
        from use of the website. Nothing in these terms limits liability that cannot be limited by law.
      </p>

      <h2>8. Governing law</h2>
      <p>These terms are governed by the laws of Pakistan, and disputes are subject to the courts of Lahore, unless a project agreement specifies otherwise.</p>

      <h2>9. Changes</h2>
      <p>We may update these terms; continued use after changes means you accept the updated terms.</p>
    </LegalPage>
  );
}
