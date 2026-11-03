import type { Metadata } from "next";
import { Container, CtaBand, PageHero } from "@/components/site/sections";
import { Reveal } from "@/components/motion/reveal";
import { benchmarkBrands, selfMeasureFields } from "@/lib/config";

export const metadata: Metadata = {
  title: "Size & Measurement Guide",
  description: "Laraib Creative standard sizes and how to measure yourself for a perfect fit.",
};

// Placeholder chart — to be finalised by the master tailor (inches).
const chart = [
  ["XS", 34, 30, 37, 13.5, 21, 38],
  ["S", 36, 32, 39, 14, 21.5, 39],
  ["M", 38, 34, 41, 14.5, 22, 40],
  ["L", 40, 36, 43, 15, 22.5, 40],
  ["XL", 42, 38, 45, 15.5, 23, 41],
  ["XXL", 44, 40, 47, 16, 23, 41],
  ["3XL", 46, 42, 49, 16.5, 23.5, 42],
];

export default function SizeGuidePage() {
  return (
    <>
      <PageHero
        eyebrow="Size guide"
        title={
          <>
            Know your size? <em className="text-wine">We&rsquo;ll match it.</em>
          </>
        }
        body={`Our standard sizes are benchmarked against brands you already wear — ${benchmarkBrands.slice(0, 5).join(", ")} and more.`}
      />
      <section className="py-20">
        <Container className="grid gap-16 lg:grid-cols-[1.4fr_1fr]">
          <Reveal className="overflow-x-auto">
            <h2 className="text-3xl text-plum">Laraib standard sizes (inches)</h2>
            <table className="mt-8 w-full min-w-[520px] text-left text-sm">
              <thead className="text-xs tracking-wider text-muted uppercase">
                <tr className="border-b border-line">
                  {["Size", "Chest", "Waist", "Hip", "Shoulder", "Sleeve", "Length"].map((h) => (
                    <th key={h} className="py-3 font-semibold">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {chart.map((row) => (
                  <tr key={row[0]} className="border-b border-dashed border-line">
                    {row.map((cell, i) => (
                      <td key={i} className={i === 0 ? "font-display py-3 text-lg text-plum" : "py-3 tabular-nums"}>
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-4 text-xs text-muted">
              Brand names are used only to help you compare sizes. Laraib Creative is not affiliated with these brands.
            </p>
          </Reveal>
          <Reveal delay={0.15}>
            <h2 className="text-3xl text-plum">Measuring yourself</h2>
            <ol className="mt-8 space-y-5">
              {selfMeasureFields.map((f, i) => (
                <li key={f.key} className="flex gap-4">
                  <span className="font-display text-gold italic">0{i + 1}</span>
                  <div>
                    <p className="font-medium">{f.label}</p>
                    <p className="text-sm text-muted">{f.hint}</p>
                  </div>
                </li>
              ))}
            </ol>
            <p className="mt-8 rounded-[var(--radius-md)] bg-cream p-5 text-sm text-muted">
              Not sure? Choose a home measurement visit or send us a suit that fits you well — we&rsquo;ll copy it.
            </p>
          </Reveal>
        </Container>
      </section>
      <CtaBand />
    </>
  );
}
