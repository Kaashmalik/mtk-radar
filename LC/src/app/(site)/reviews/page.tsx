import type { Metadata } from "next";
import { Container, CtaBand, PageHero, ReviewsGrid, Stars } from "@/components/site/sections";
import { getPublishedReviews } from "@/lib/data/public";

export const metadata: Metadata = {
  title: "Customer Reviews",
  description: "Verified reviews from Laraib Creative customers — only delivered orders can be reviewed.",
};

export default async function ReviewsPage() {
  const { reviews, preview } = await getPublishedReviews();
  const avg = reviews.length ? reviews.reduce((s, r) => s + r.rating, 0) / reviews.length : 0;

  return (
    <>
      <PageHero
        eyebrow="Reviews"
        title={
          <>
            Written by customers <em className="text-wine">who wore it.</em>
          </>
        }
        body="Every review is linked to a delivered order. We publish the critical ones too — and reply to them."
      />
      <section className="py-20">
        <Container>
          {reviews.length > 0 && !preview && (
            <div className="mb-12 flex flex-wrap items-center gap-6 rounded-[var(--radius-lg)] border border-line p-8">
              <p className="font-display text-6xl text-plum">{avg.toFixed(1)}</p>
              <div>
                <Stars value={Math.round(avg)} />
                <p className="mt-1 text-sm text-muted">{reviews.length} verified reviews</p>
              </div>
            </div>
          )}
          <ReviewsGrid reviews={reviews} preview={preview} />
        </Container>
      </section>
      <CtaBand />
    </>
  );
}
