import type { Metadata } from 'next';
import { pageMeta } from '@/lib/seo';
import { site } from '@/data/site';
import LegalPage from '@/components/ui/LegalPage';
import CookieSettingsButton from '@/components/layout/CookieSettingsButton';

export const metadata: Metadata = pageMeta({
  title: 'Cookie Policy',
  description: `Which cookies ${site.name} uses, why, and how to change your choices.`,
  path: '/cookies',
});

const rows = [
  ['mtk_consent', 'Essential', 'Remembers your cookie choices', '6 months'],
  ['theme (local storage)', 'Essential', 'Remembers light/dark mode', 'Until cleared'],
  ['mtk-announcement-dismissed-v1 (local storage)', 'Essential', 'Remembers that you closed the announcement bar', 'Until cleared'],
  ['_ga, _ga_*', 'Analytics', 'Google Analytics — distinguishes visitors and sessions', 'Up to 2 years'],
  ['NID, AEC (google.com)', 'Functional', 'Google Maps embed on contact & location pages', 'Up to 6 months'],
  ['__gads, __gpi, IDE, NID', 'Advertising', 'Google AdSense — ad delivery, frequency capping and personalisation', 'Up to 13 months'],
];

export default function CookiesPage() {
  return (
    <LegalPage
      current="/cookies"
      title="Cookie Policy"
      intro="Cookies are small text files stored on your device. We use a few essential cookies to run this site and, only with your permission, analytics and advertising cookies."
    >
      <h2>Your choices</h2>
      <p>
        When you first visit, a banner lets you accept all, reject non-essential, or customise. Non-essential cookies stay off until you opt in, and we use
        Google Consent Mode v2 so Google services respect your choice. You can change your mind at any time:
      </p>
      <p>
        <CookieSettingsButton className="rounded-full bg-cta px-5 py-2.5 text-sm font-semibold text-on-cta hover:bg-cta-hover" />
      </p>

      <h2>Cookies we use</h2>
      <p>
        Our traffic analytics are first-party and cookieless: no cookie, pixel or device identifier is created. You are not in the table below because
        nothing is stored on your device for measurement.
      </p>
      <div className="not-prose overflow-x-auto rounded-xl border border-line">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="bg-muted text-fg">
            <tr>
              {['Name', 'Category', 'Purpose', 'Duration'].map((h) => (
                <th key={h} className="px-4 py-3 font-semibold">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r[0]} className="border-t border-line">
                {r.map((c, i) => (
                  <td key={i} className={`px-4 py-3 ${i === 0 ? 'font-mono text-xs text-fg' : ''}`}>
                    {c}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Third-party cookies</h2>
      <p>
        Third-party analytics and advertising cookies are set by Google and only load after you accept them. See{' '}
        <a href="https://policies.google.com/technologies/cookies" target="_blank" rel="noopener noreferrer">
          Google&apos;s cookie information
        </a>{' '}
        for details and{' '}
        <a href="https://adssettings.google.com" target="_blank" rel="noopener noreferrer">
          Ads Settings
        </a>{' '}
        to manage ad personalisation.
      </p>

      <h2>Browser controls</h2>
      <p>You can also block or delete cookies in your browser settings. Blocking essential cookies may affect how the site works.</p>
    </LegalPage>
  );
}
