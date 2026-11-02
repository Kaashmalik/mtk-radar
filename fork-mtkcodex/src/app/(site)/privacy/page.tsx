import type { Metadata } from 'next';
import { pageMeta } from '@/lib/seo';
import { site } from '@/data/site';
import LegalPage from '@/components/ui/LegalPage';

export const metadata: Metadata = pageMeta({
  title: 'Privacy Policy',
  description: `How ${site.name} collects, uses and protects personal information on this website and in client projects.`,
  path: '/privacy',
});

export default function PrivacyPage() {
  return (
    <LegalPage
      current="/privacy"
      title="Privacy Policy"
      intro={`This Privacy Policy explains how ${site.name} ("we", "us") collects, uses, shares and protects personal information when you visit ${site.url} or contact us about our products and services.`}
    >
      <h2>1. Information we collect</h2>
      <ul>
        <li>
          <strong>Information you give us:</strong> your name, email, phone/WhatsApp number, company, budget and project details when you submit the contact
          form, email us or message us.
        </li>
        <li>
          <strong>Usage data:</strong> we measure traffic with our own first-party analytics. It is cookieless: no cookie or identifier is stored on your
          device. We record the page path, referring site (hostname only), device type, approximate location (city, region, country and timezone, with
          coordinates rounded to about 10 km, as provided by our hosting provider) and a pseudonymous visitor id that is derived from your IP
          address and browser and is reset every day, so it cannot be traced back to you. Bots and admin pages are excluded. If you opt out of analytics,
          set Do Not Track or send Global Privacy Control, we do not measure your visit at all.
        </li>
        <li>
          <strong>Live chat:</strong> if you use the chat on our website, we store your messages, the page you started from, your device type and
          approximate location so our team can reply in your local time. If you share your name, email or phone in the chat, we use them only to answer
          you, including by email if you leave the site. Your browser keeps a random chat key in local storage so you can continue the conversation;
          clearing site data removes it.
        </li>
        <li>
          <strong>Cookies and similar technologies:</strong> see our <a href="/cookies">Cookie Policy</a>. Third-party analytics and advertising scripts
          only run after you accept them.
        </li>
      </ul>

      <h2>2. How we use information</h2>
      <ul>
        <li>To reply to enquiries, prepare quotes, schedule demos and deliver our services.</li>
        <li>To operate, secure and improve the website.</li>
        <li>To measure performance and, if you consent, show relevant advertising.</li>
        <li>To comply with legal obligations and enforce our terms.</li>
      </ul>
      <p>We do not sell your personal information.</p>

      <h2>3. Legal bases (EEA/UK visitors)</h2>
      <p>
        We process data on the basis of your legitimate interests (cookieless traffic measurement that does not identify you, responding to enquiries,
        securing the site), your consent (third-party analytics and advertising cookies) and the performance of a contract (delivering services you request).
      </p>

      <h2>4. Advertising and Google AdSense</h2>
      <p>
        This site may display ads served by Google AdSense. Third-party vendors, including Google, use cookies to serve ads based on your prior visits to
        this and other websites. Google&apos;s use of advertising cookies enables it and its partners to serve ads based on your visits. You can opt out of
        personalised advertising at{' '}
        <a href="https://adssettings.google.com" target="_blank" rel="noopener noreferrer">
          Google Ads Settings
        </a>{' '}
        or{' '}
        <a href="https://www.aboutads.info/choices" target="_blank" rel="noopener noreferrer">
          aboutads.info
        </a>
        . Learn more in{' '}
        <a href="https://policies.google.com/technologies/partner-sites" target="_blank" rel="noopener noreferrer">
          How Google uses information from sites that use its services
        </a>
        . Advertising cookies are only set after you accept them in our cookie banner.
      </p>

      <h2>5. Sharing</h2>
      <p>
        We share information only with service providers that help us run the business — for example hosting and database (Vercel, Supabase), email
        delivery (Resend), and advertising (Google) — under appropriate confidentiality and data-protection terms, or when required by law. Our traffic
        analytics run on our own infrastructure and are not shared with third parties.
      </p>

      <h2>6. Client project data</h2>
      <p>
        When we build or maintain software for clients, we act as a processor of the client&apos;s data and handle it only on the client&apos;s documented
        instructions, under a separate agreement. Our web-scraping services collect publicly available information only and respect website terms,
        robots.txt and applicable data-protection laws.
      </p>

      <h2>7. Retention and security</h2>
      <p>
        We keep enquiry data for as long as needed to respond and maintain our business relationship, typically no longer than 24 months after last contact.
        Cookieless traffic records are deleted after 180 days. We use HTTPS, access controls and reputable providers to protect information, but no method of
        transmission is 100% secure.
      </p>

      <h2>8. Your rights</h2>
      <p>
        Depending on where you live, you may request access to, correction, deletion or a copy of your personal data, object to or restrict processing, and
        withdraw consent at any time via &ldquo;Cookie settings&rdquo; in the footer. Email us to make a request.
      </p>

      <h2>9. Children</h2>
      <p>This website is intended for businesses and is not directed at children under 13. We do not knowingly collect their data.</p>

      <h2>10. Changes</h2>
      <p>We may update this policy. The &ldquo;last updated&rdquo; date above shows when it last changed.</p>
    </LegalPage>
  );
}
