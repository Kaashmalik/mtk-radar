import { Container, PageHero } from "@/components/site/sections";
import { breadcrumbLd, JsonLd } from "@/lib/seo";

export function LegalPage({
  eyebrow,
  title,
  path,
  updated,
  sections,
}: {
  eyebrow: string;
  title: string;
  path: string;
  updated: string;
  sections: { heading: string; body: (string | string[])[] }[];
}) {
  return (
    <>
      <JsonLd data={breadcrumbLd([{ name: title, path }])} />
      <PageHero eyebrow={eyebrow} title={title} body={`Last updated ${updated}`} />
      <section className="py-16">
        <Container className="max-w-3xl space-y-10">
          {sections.map((s) => (
            <div key={s.heading}>
              <h2 className="text-2xl text-plum">{s.heading}</h2>
              {s.body.map((b, i) =>
                Array.isArray(b) ? (
                  <ul key={i} className="mt-3 list-disc space-y-1.5 pl-5 text-ink/85">
                    {b.map((li) => (
                      <li key={li}>{li}</li>
                    ))}
                  </ul>
                ) : (
                  <p key={i} className="mt-3 leading-relaxed text-ink/85">
                    {b}
                  </p>
                ),
              )}
            </div>
          ))}
        </Container>
      </section>
    </>
  );
}
