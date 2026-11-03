import type { Metadata } from "next";
import { Container, CtaBand, PageHero, ZonesSection } from "@/components/site/sections";
import { ThreadSteps } from "@/components/motion/thread-steps";
import { Reveal } from "@/components/motion/reveal";
import { faqs, journeySteps } from "@/lib/content";
import { breadcrumbLd, faqLd, JsonLd } from "@/lib/seo";

export const metadata: Metadata = {
  title: "How It Works",
  description: "Design online, choose how we measure you, pay by transfer, and our riders handle pickup and delivery.",
};

export default function HowItWorksPage() {
  return (
    <>
      <JsonLd data={[faqLd(faqs), breadcrumbLd([{ name: "How it works", path: "/how-it-works" }])]} />
      <PageHero
        eyebrow="How it works"
        title={
          <>
            Six steps. <em className="text-wine">Zero trips to the tailor.</em>
          </>
        }
      />
      <section className="py-24">
        <Container>
          <ThreadSteps steps={journeySteps} />
        </Container>
      </section>
      <ZonesSection />
      <section className="bg-cream/60 py-24">
        <Container className="max-w-3xl">
          <p className="eyebrow">Questions</p>
          <h2 className="mt-3 text-4xl text-plum">Good to know</h2>
          <div className="mt-10 divide-y divide-line border-y border-line">
            {faqs.map((f, i) => (
              <Reveal key={f.q} delay={i * 0.05}>
                <details className="group py-6">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-6 text-lg text-ink">
                    {f.q}
                    <span className="font-display text-2xl text-gold transition-transform duration-300 group-open:rotate-45">+</span>
                  </summary>
                  <p className="mt-4 leading-relaxed text-muted">{f.a}</p>
                </details>
              </Reveal>
            ))}
          </div>
        </Container>
      </section>
      <div className="pt-24">
        <CtaBand />
      </div>
    </>
  );
}
