import type { Metadata } from "next";
import { Clock, MapPin, MessageCircle, Phone } from "lucide-react";
import { Container, PageHero } from "@/components/site/sections";
import { Reveal } from "@/components/motion/reveal";
import { InquiryForm } from "@/components/site/inquiry-form";
import { brand, whatsappLink } from "@/lib/config";

export const metadata: Metadata = {
  title: "Visit Our Studio — Garhi Shahu, Lahore",
  description: "Laraib Creative studio and warehouse on Allama Iqbal Road, near Pakistan Railways Headquarters, Garhi Shahu, Lahore.",
};

export default function ContactPage() {
  const details = [
    { icon: MapPin, label: "Studio & warehouse", value: brand.address, href: brand.mapsUrl },
    { icon: Clock, label: "Hours", value: brand.hours },
    { icon: Phone, label: "Call", value: brand.phone, href: `tel:${brand.phone.replace(/\s/g, "")}` },
    { icon: MessageCircle, label: "WhatsApp", value: "Chat with us", href: whatsappLink("Assalam o Alaikum Laraib Creative!") },
  ];

  return (
    <>
      <PageHero
        eyebrow="Visit us"
        title={
          <>
            Near Railway Headquarters, <em className="text-wine">Garhi Shahu.</em>
          </>
        }
        body="Drop off your fabric, get measured in our fitting room, or ask us anything about bridal and custom work."
      />
      <section className="py-20">
        <Container className="grid gap-16 lg:grid-cols-[1fr_1.2fr]">
          <Reveal className="space-y-8">
            {details.map(({ icon: Icon, label, value, href }) => (
              <div key={label} className="flex gap-4">
                <span className="grid size-11 shrink-0 place-items-center rounded-full border border-line text-gold">
                  <Icon className="size-4" />
                </span>
                <div>
                  <p className="text-xs font-semibold tracking-[0.2em] text-muted uppercase">{label}</p>
                  {href ? (
                    <a href={href} target="_blank" rel="noopener noreferrer" className="link-thread mt-1 inline-block text-lg text-ink">
                      {value}
                    </a>
                  ) : (
                    <p className="mt-1 text-lg">{value}</p>
                  )}
                </div>
              </div>
            ))}
            <div className="overflow-hidden rounded-[var(--radius-lg)] border border-line">
              <iframe
                title="Laraib Creative location map"
                src="https://www.google.com/maps?q=Pakistan+Railways+Headquarters+Garhi+Shahu+Lahore&output=embed"
                className="h-72 w-full grayscale-[40%]"
                loading="lazy"
                referrerPolicy="no-referrer-when-downgrade"
              />
            </div>
          </Reveal>
          <Reveal delay={0.15} id="inquiry">
            <p className="eyebrow">Inquiry & quotes</p>
            <h2 className="mt-3 mb-8 text-4xl text-plum">Tell us what you have in mind</h2>
            <InquiryForm />
          </Reveal>
        </Container>
      </section>
    </>
  );
}
