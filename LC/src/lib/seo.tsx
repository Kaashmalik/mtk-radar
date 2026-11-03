import { brand, garments } from "@/lib/config";

export const SITE_URL = `https://${brand.domain}`;

// Approximate pin for Pakistan Railways HQ, Garhi Shahu — confirm against your Google Business Profile.
const GEO = { latitude: 31.5636, longitude: 74.3384 };

export function JsonLd({ data }: { data: object | object[] }) {
  return <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, "\\u003c") }} />;
}

export const organizationLd = {
  "@context": "https://schema.org",
  "@type": "Organization",
  "@id": `${SITE_URL}/#organization`,
  name: brand.name,
  url: SITE_URL,
  logo: `${SITE_URL}/brand-icon/512.png`,
  sameAs: [brand.instagram, brand.facebook, brand.tiktok],
  contactPoint: [{ "@type": "ContactPoint", telephone: brand.phone, contactType: "customer service", areaServed: "PK", availableLanguage: ["en", "ur"] }],
};

export const websiteLd = {
  "@context": "https://schema.org",
  "@type": "WebSite",
  "@id": `${SITE_URL}/#website`,
  url: SITE_URL,
  name: brand.name,
  publisher: { "@id": `${SITE_URL}/#organization` },
  inLanguage: "en-PK",
};

export function localBusinessLd(areaServed: string[] = ["Lahore"]) {
  return {
    "@context": "https://schema.org",
    "@type": ["ClothingStore", "LocalBusiness"],
    "@id": `${SITE_URL}/#business`,
    name: `${brand.name} — Ladies Tailoring`,
    description: "Premium ladies suit stitching in Lahore with doorstep fabric pickup by our own riders, saved measurements and live order tracking.",
    url: SITE_URL,
    image: `${SITE_URL}/opengraph-image`,
    logo: `${SITE_URL}/brand-icon/512.png`,
    telephone: brand.phone,
    email: brand.email,
    priceRange: "Rs 1,400 – Rs 15,000+",
    currenciesAccepted: "PKR",
    paymentAccepted: "Bank transfer, JazzCash, Easypaisa, Raast, Cash",
    address: {
      "@type": "PostalAddress",
      streetAddress: "Allama Iqbal Road, near Pakistan Railways Headquarters, Garhi Shahu",
      addressLocality: "Lahore",
      addressRegion: "Punjab",
      postalCode: "54000",
      addressCountry: "PK",
    },
    geo: { "@type": "GeoCoordinates", ...GEO },
    hasMap: brand.mapsUrl,
    openingHoursSpecification: [
      {
        "@type": "OpeningHoursSpecification",
        dayOfWeek: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
        opens: "11:00",
        closes: "20:00",
      },
    ],
    areaServed: areaServed.map((name) => ({ "@type": "Place", name })),
    parentOrganization: { "@id": `${SITE_URL}/#organization` },
    hasOfferCatalog: {
      "@type": "OfferCatalog",
      name: "Stitching services",
      itemListElement: garments.map((g) => ({
        "@type": "Offer",
        priceCurrency: "PKR",
        price: g.basePrice,
        priceSpecification: { "@type": "PriceSpecification", minPrice: g.basePrice, priceCurrency: "PKR" },
        itemOffered: { "@type": "Service", name: `${g.name} stitching`, description: g.blurb },
      })),
    },
  };
}

export function breadcrumbLd(items: { name: string; path: string }[]) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [{ name: "Home", path: "/" }, ...items].map((it, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: it.name,
      item: `${SITE_URL}${it.path}`,
    })),
  };
}

export function faqLd(faqs: { q: string; a: string }[]) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })),
  };
}

export function articleLd(a: { slug: string; title: string; excerpt: string; published: string }) {
  return {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: a.title,
    description: a.excerpt,
    datePublished: a.published,
    dateModified: a.published,
    mainEntityOfPage: `${SITE_URL}/journal/${a.slug}`,
    image: `${SITE_URL}/opengraph-image`,
    author: { "@type": "Organization", name: brand.name, url: SITE_URL },
    publisher: { "@id": `${SITE_URL}/#organization` },
    inLanguage: "en-PK",
  };
}
