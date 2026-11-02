import { fullAddress, maps, site } from '@/data/site';
import { products } from '@/data/products';
import { services } from '@/data/services';
import { industries } from '@/data/content';
import { getPosts } from '@/lib/blog';

export const dynamic = 'force-static';

// llms.txt: a plain-language map of the site for AI assistants and answer engines.
export function GET() {
  const u = (p: string) => `${site.url}${p}`;
  const body = `# ${site.name}

> ${site.slogan} ${site.tagline}

${site.name} is a software company based in Lahore, Pakistan, serving clients worldwide. Founded by ${site.founder.name} (${site.founder.role}).
Also known as: ${site.alternateNames.join(', ')}.
Address: ${fullAddress} · Map: ${maps.open} · Hours: ${site.openingHours.label}
Contact: ${site.email} · ${site.phone} · WhatsApp https://wa.me/${site.whatsapp}

## Products
${products.map((p) => `- [${p.name}](${u(`/products/${p.slug}`)}): ${p.cloud}. ${p.description}`).join('\n')}

## Services
${services.map((s) => `- [${s.title}](${u(`/services/${s.id}`)}): ${s.summary}`).join('\n')}

## Industries
${industries.map((i) => `- [${i.name}](${u(`/industries/${i.id}`)}): ${i.headline}`).join('\n')}

## Company
- [Platform](${u('/platform')}): the shared multi-tenant, secure, automation- and AI-ready foundation behind every product.
- [Customer stories](${u('/customers')})
- [Pricing](${u('/pricing')})
- [About & leadership](${u('/about')})
- [Contact / book a demo](${u('/contact')})

## Insights
${getPosts().map((p) => `- [${p.title}](${u(`/blog/${p.slug}`)}): ${p.summary}`).join('\n')}
`;
  return new Response(body, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
}
