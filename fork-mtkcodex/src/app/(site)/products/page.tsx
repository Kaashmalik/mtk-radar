import type { Metadata } from 'next';
import { pageMeta } from '@/lib/seo';
import PageHeader from '@/components/ui/PageHeader';
import { Button } from '@/components/ui/primitives';
import ProductSuite from '@/components/sections/ProductSuite';
import DemoShowcase from '@/components/sections/DemoShowcase';
import CtaBand from '@/components/sections/CtaBand';

export const metadata: Metadata = pageMeta({
  title: 'SaaS Projects & Products',
  description: 'Seven production-ready, multi-tenant SaaS platforms by MTK Codex: sports league management, dairy farm management, fashion e-commerce, installment finance, school management, AI security and desktop apps.',
  path: '/products',
  keywords: ['SaaS projects', 'SaaS project examples', 'SaaS products', 'white-label SaaS', 'cricket league software', 'dairy farm software', 'school management system', 'installment management software'],
});

export default function ProductsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Products"
        title={
          <>
            SaaS platforms, <span className="text-gradient">ready for your brand.</span>
          </>
        }
        text="Subscribe, white-label or extend. Every MTK Codex product is multi-tenant, secure and built on a modern, scalable stack."
      >
        <Button href="/contact?intent=demo" size="lg" arrow>
          Book a guided demo
        </Button>
        <Button href="#demos" size="lg" variant="secondary">
          Try live previews
        </Button>
      </PageHeader>
      <ProductSuite />
      <DemoShowcase />
      <CtaBand title="Want one of these under your brand?" text="We configure your logo, domain, roles and data — then train your team. Launch in days, not months." />
    </>
  );
}
