import { Hero } from "@/components/site/home/hero";
import { Marquee } from "@/components/site/home/marquee";
import {
  Container,
  CraftSection,
  CtaBand,
  MeasurementOptions,
  Promises,
  ReviewsGrid,
  SectionHeading,
  ServicesGrid,
  ZonesSection,
} from "@/components/site/sections";
import { ThreadSteps } from "@/components/motion/thread-steps";
import { ButtonLink } from "@/components/ui/button";
import { journeySteps } from "@/lib/content";
import { GalleryGrid } from "@/components/site/gallery";
import { getGallery, getPublishedReviews, getSiteMedia } from "@/lib/data/public";
import { JsonLd, localBusinessLd } from "@/lib/seo";
import { areas } from "@/lib/content/areas";

export default async function HomePage() {
  const [{ reviews, preview }, { items }, media] = await Promise.all([getPublishedReviews(), getGallery(), getSiteMedia()]);

  return (
    <>
      <JsonLd data={localBusinessLd(["Lahore", ...areas.map((a) => a.name)])} />
      <Hero media={media} />
      <Marquee />
      <Promises />
      <CraftSection media={media} />

      <section className="bg-cream/60 py-24 md:py-32">
        <Container>
          <SectionHeading
            align="center"
            eyebrow="How it works"
            title={
              <>
                From your cupboard to <em className="text-wine">your door</em>, stitched.
              </>
            }
          />
          <div className="mt-20">
            <ThreadSteps steps={journeySteps} />
          </div>
        </Container>
      </section>

      <section className="py-24 md:py-32">
        <Container>
          <div className="flex flex-wrap items-end justify-between gap-6">
            <SectionHeading eyebrow="Services" title="What we stitch" />
            <ButtonLink href="/pricing" variant="outline">
              Full price list
            </ButtonLink>
          </div>
          <div className="mt-14">
            <ServicesGrid media={media} />
          </div>
        </Container>
      </section>

      <MeasurementOptions />

      <section className="py-24 md:py-32">
        <Container>
          <div className="flex flex-wrap items-end justify-between gap-6">
            <SectionHeading
              eyebrow="Stitched by Laraib"
              title={
                <>
                  Real orders, <em className="text-wine">shared with consent.</em>
                </>
              }
            />
            <ButtonLink href="/gallery" variant="outline">
              View the gallery
            </ButtonLink>
          </div>
          <div className="mt-14">
            <GalleryGrid items={items} filters={false} limit={8} />
          </div>
        </Container>
      </section>

      <ZonesSection />

      <section className="bg-cream/60 py-24 md:py-32">
        <Container>
          <SectionHeading eyebrow="Reviews" title="Only from delivered orders" />
          <div className="mt-14">
            <ReviewsGrid reviews={reviews.slice(0, 6)} preview={preview} />
          </div>
        </Container>
      </section>

      <div className="pt-24">
        <CtaBand />
      </div>
    </>
  );
}
