import Hero from '@/components/sections/Hero';
import ProductStrip from '@/components/sections/ProductStrip';
import Stats from '@/components/sections/Stats';
import ProductSuite from '@/components/sections/ProductSuite';
import DemoShowcase from '@/components/sections/DemoShowcase';
import ServicesGrid from '@/components/sections/ServicesGrid';
import Automation from '@/components/sections/Automation';
import Industries from '@/components/sections/Industries';
import Process from '@/components/sections/Process';
import Testimonials from '@/components/sections/Testimonials';
import Founder from '@/components/sections/Founder';
import Engagement from '@/components/sections/Engagement';
import Faq from '@/components/sections/Faq';
import CtaBand from '@/components/sections/CtaBand';
import PlatformDiagram from '@/components/sections/PlatformDiagram';
import ImpactDashboard from '@/components/sections/ImpactDashboard';
import InfinityLoop from '@/components/sections/InfinityLoop';
import ScrapingShowcase from '@/components/sections/ScrapingShowcase';
import CrmShowcase from '@/components/sections/CrmShowcase';

export default function HomePage() {
  return (
    <>
      <Hero />
      <ProductStrip />
      <Stats />
      <PlatformDiagram />
      <ProductSuite />
      <DemoShowcase />
      <ServicesGrid />
      <InfinityLoop />
      <ScrapingShowcase />
      <CrmShowcase />
      <Automation />
      <ImpactDashboard />
      <Industries />
      <Process />
      <Testimonials />
      <Founder />
      <Engagement />
      <Faq />
      <CtaBand />
    </>
  );
}
