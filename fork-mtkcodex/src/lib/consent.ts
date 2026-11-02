// Cookie-consent state shared by the banner, footer link and third-party scripts.

export type Consent = { analytics: boolean; ads: boolean; ts: number };

export const CONSENT_COOKIE = 'mtk_consent';
export const CONSENT_MAX_AGE = 60 * 60 * 24 * 180; // re-ask after ~6 months
export const OPEN_SETTINGS_EVENT = 'mtk:open-cookie-settings';

export function readConsent(): Consent | null {
  if (typeof document === 'undefined') return null;
  const raw = document.cookie.split('; ').find((c) => c.startsWith(`${CONSENT_COOKIE}=`));
  if (!raw) return null;
  try {
    return JSON.parse(decodeURIComponent(raw.split('=')[1])) as Consent;
  } catch {
    return null;
  }
}

type Gtag = (...args: unknown[]) => void;

export function writeConsent(c: Omit<Consent, 'ts'>) {
  const value: Consent = { ...c, ts: Date.now() };
  const secure = location.protocol === 'https:' ? '; Secure' : '';
  document.cookie = `${CONSENT_COOKIE}=${encodeURIComponent(JSON.stringify(value))}; Max-Age=${CONSENT_MAX_AGE}; Path=/; SameSite=Lax${secure}`;
  applyConsent(value);
  return value;
}

/** Pushes the choice to Google Consent Mode v2 (no-op if gtag isn't loaded). */
export function applyConsent(c: Pick<Consent, 'analytics' | 'ads'>) {
  const gtag = (window as unknown as { gtag?: Gtag }).gtag;
  gtag?.('consent', 'update', {
    analytics_storage: c.analytics ? 'granted' : 'denied',
    ad_storage: c.ads ? 'granted' : 'denied',
    ad_user_data: c.ads ? 'granted' : 'denied',
    ad_personalization: c.ads ? 'granted' : 'denied',
  });
}

export const openCookieSettings = () => window.dispatchEvent(new Event(OPEN_SETTINGS_EVENT));
