import Script from 'next/script';

const GA_ID = process.env.NEXT_PUBLIC_GA_ID;
export const ADSENSE_CLIENT = process.env.NEXT_PUBLIC_ADSENSE_CLIENT; // e.g. ca-pub-1234567890123456

/**
 * Google Consent Mode v2: everything is denied by default until the visitor chooses in the
 * cookie banner. Analytics and AdSense load only when their IDs are configured.
 */
const consentDefaults = `window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}window.gtag=gtag;
gtag('consent','default',{ad_storage:'denied',ad_user_data:'denied',ad_personalization:'denied',analytics_storage:'denied',functionality_storage:'granted',security_storage:'granted',wait_for_update:500});
gtag('set','ads_data_redaction',true);gtag('set','url_passthrough',true);
try{var m=document.cookie.match(/(?:^|; )mtk_consent=([^;]+)/);if(m){var c=JSON.parse(decodeURIComponent(m[1]));gtag('consent','update',{analytics_storage:c.analytics?'granted':'denied',ad_storage:c.ads?'granted':'denied',ad_user_data:c.ads?'granted':'denied',ad_personalization:c.ads?'granted':'denied'});}}catch(e){}`;

export function ConsentDefaults() {
  return <script dangerouslySetInnerHTML={{ __html: consentDefaults }} />;
}

export default function ThirdPartyScripts() {
  return (
    <>
      {GA_ID && (
        <>
          <Script src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`} strategy="afterInteractive" />
          <Script id="ga4" strategy="afterInteractive">{`gtag('js', new Date()); gtag('config', '${GA_ID}', { anonymize_ip: true });`}</Script>
        </>
      )}
      {ADSENSE_CLIENT && (
        <Script
          id="adsense"
          async
          strategy="afterInteractive"
          crossOrigin="anonymous"
          src={`https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${ADSENSE_CLIENT}`}
        />
      )}
    </>
  );
}
