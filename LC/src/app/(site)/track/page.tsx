import type { Metadata } from "next";
import { Container, PageHero } from "@/components/site/sections";
import { TrackForm } from "@/components/site/track-form";

export const metadata: Metadata = {
  title: "Track Your Order",
  description: "Follow your Laraib Creative order from fabric pickup to delivery.",
};

export default function TrackPage() {
  return (
    <>
      <PageHero
        eyebrow="Track order"
        title={
          <>
            Where is <em className="text-wine">my suit?</em>
          </>
        }
        body="Enter your order number and the mobile number you ordered with."
      />
      <section className="py-20">
        <Container>
          <TrackForm />
        </Container>
      </section>
    </>
  );
}
