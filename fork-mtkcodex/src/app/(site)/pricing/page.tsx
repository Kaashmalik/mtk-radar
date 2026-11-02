import type { Metadata } from 'next';
import { pageMeta } from '@/lib/seo';
import PageHeader from '@/components/ui/PageHeader';
import Engagement from '@/components/sections/Engagement';
import Faq from '@/components/sections/Faq';
import CtaBand from '@/components/sections/CtaBand';

export const metadata: Metadata = pageMeta({
  title: 'Pricing',
  description: 'Transparent pricing: SaaS subscriptions, fixed-quote custom software projects and monthly care & growth plans.',
  path: '/pricing',
  keywords: ['software development pricing', 'SaaS pricing', 'maintenance plan'],
});

export default function PricingPage() {
  return (
    <>
      <PageHeader
        eyebrow="Pricing"
        title={
          <>
            Simple plans. <span className="text-gradient">No surprises.</span>
          </>
        }
        text="Every engagement starts with a free consultation. Final pricing depends on scope, users and integrations — and is always agreed in writing first."
      />
      <Engagement heading={false} />
      <Faq />
      <CtaBand />
    </>
  );
}
