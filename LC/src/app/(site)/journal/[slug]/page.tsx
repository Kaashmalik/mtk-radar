import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { articles } from "@/lib/content/journal";
import { articleLd, breadcrumbLd, JsonLd } from "@/lib/seo";
import { Container, CtaBand } from "@/components/site/sections";
import { Reveal } from "@/components/motion/reveal";
import { AdSlot } from "@/components/site/consent";
import { ButtonLink } from "@/components/ui/button";
import { formatDay } from "@/lib/pricing";

export function generateStaticParams() {
  return articles.map((a) => ({ slug: a.slug }));
}

export async function generateMetadata({ params }: PageProps<"/journal/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  const a = articles.find((x) => x.slug === slug);
  if (!a) return {};
  return {
    title: a.title,
    description: a.excerpt,
    alternates: { canonical: `/journal/${a.slug}` },
    openGraph: { type: "article", title: a.title, description: a.excerpt, publishedTime: a.published },
  };
}

const AD_SLOT = process.env.NEXT_PUBLIC_ADSENSE_SLOT_ARTICLE ?? "";

export default async function ArticlePage({ params }: PageProps<"/journal/[slug]">) {
  const { slug } = await params;
  const a = articles.find((x) => x.slug === slug);
  if (!a) notFound();
  const more = articles.filter((x) => x.slug !== a.slug).slice(0, 3);

  return (
    <>
      <JsonLd data={[articleLd(a), breadcrumbLd([{ name: "Style Journal", path: "/journal" }, { name: a.title, path: `/journal/${a.slug}` }])]} />
      <article className="grain pt-36 pb-20 md:pt-44">
        <Container className="max-w-3xl">
          <nav aria-label="Breadcrumb" className="text-sm text-muted">
            <Link href="/journal" className="hover:text-plum">Style Journal</Link> / <span>{a.category}</span>
          </nav>
          <h1 className="mt-6 text-[clamp(2.2rem,5vw,3.6rem)] leading-[1.05] text-plum">{a.title}</h1>
          <p className="mt-5 text-lg text-muted">{a.excerpt}</p>
          <p className="mt-6 text-sm text-muted">
            By the Laraib Creative workshop · <time dateTime={a.published}>{formatDay(a.published)}</time> · {a.readMinutes} min read
          </p>
          <div className="stitch-rule mt-10" />

          <div className="mt-10 space-y-12">
            {a.sections.map((s, i) => (
              <Reveal key={s.heading}>
                <h2 className="text-2xl text-plum md:text-3xl">{s.heading}</h2>
                {s.body.map((p, j) => (
                  <p key={j} className="mt-4 text-[1.06rem] leading-[1.8] text-ink/85">
                    {p}
                  </p>
                ))}
                {/* one ad after the second section only, kept away from calls to action */}
                {i === 1 && <AdSlot slot={AD_SLOT} className="mt-10" />}
              </Reveal>
            ))}
          </div>

          <div className="mt-16 rounded-[var(--radius-lg)] bg-plum p-8 text-ivory">
            <p className="font-display text-2xl">Let us stitch it for you</p>
            <p className="mt-2 text-ivory/75">Rider pickup across Lahore, saved measurements and a delivery date you can count on.</p>
            <ButtonLink href="/order" variant="gold" className="mt-6">
              Start an order
            </ButtonLink>
          </div>

          <h2 className="mt-16 text-xl text-plum">Keep reading</h2>
          <ul className="mt-5 space-y-3">
            {more.map((m) => (
              <li key={m.slug}>
                <Link href={`/journal/${m.slug}`} className="link-thread text-ink/85 hover:text-plum">
                  {m.title}
                </Link>
              </li>
            ))}
          </ul>
        </Container>
      </article>
      <CtaBand />
    </>
  );
}
