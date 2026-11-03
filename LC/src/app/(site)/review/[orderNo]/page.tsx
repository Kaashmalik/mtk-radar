import { Suspense } from "react";
import type { Metadata } from "next";
import { Container } from "@/components/site/sections";
import { ReviewForm } from "@/components/site/review-form";

export const metadata: Metadata = { title: "Review your order", robots: { index: false } };

async function ReviewContent({ params, searchParams }: PageProps<"/review/[orderNo]">) {
  const [{ orderNo }, sp] = await Promise.all([params, searchParams]);
  const token = typeof sp.t === "string" ? sp.t : "";
  const order = decodeURIComponent(orderNo).toUpperCase();
  if (!/^LC-\d+$/.test(order) || !token) {
    return <p className="text-muted">This review link is incomplete. Please use the link from your WhatsApp message.</p>;
  }
  return (
    <>
      <p className="mb-8 text-muted">
        Order <strong className="text-ink">{order}</strong>
      </p>
      <ReviewForm orderNo={order} token={token} />
    </>
  );
}

export default function ReviewPage(props: PageProps<"/review/[orderNo]">) {
  return (
    <section className="grain pt-36 pb-24 md:pt-44">
      <Container className="max-w-xl">
        <p className="eyebrow">Your review</p>
        <h1 className="mt-3 text-4xl text-plum">
          How did we <em className="text-wine">do?</em>
        </h1>
        <div className="mt-6">
          <Suspense>
            <ReviewContent {...props} />
          </Suspense>
        </div>
      </Container>
    </section>
  );
}
