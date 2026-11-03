import type { Metadata } from "next";
import { Container, CtaBand, PageHero } from "@/components/site/sections";
import { GalleryGrid } from "@/components/site/gallery";
import { getGallery } from "@/lib/data/public";

export const metadata: Metadata = {
  title: "Stitched by Laraib — Gallery",
  description: "Real suits stitched for our customers in Lahore, shared with their consent.",
};

export default async function GalleryPage() {
  const { items } = await getGallery();
  return (
    <>
      <PageHero
        eyebrow="Stitched by Laraib"
        title={
          <>
            Every piece here <em className="text-wine">left our workshop.</em>
          </>
        }
        body="Photographed at quality check and shared only when the customer said yes. Faces are never shown."
      />
      <section className="py-20">
        <Container>
          <GalleryGrid items={items} />
        </Container>
      </section>
      <CtaBand />
    </>
  );
}
