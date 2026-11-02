import { products } from '@/data/products';

export default function ProductStrip() {
  const row = [...products, ...products];
  return (
    <section aria-label="MTK Codex platforms" className="border-y border-line bg-elevated py-8">
      <p className="container-x mb-6 text-center text-xs font-semibold uppercase tracking-[0.18em] text-fg-subtle">
        Platforms engineered by MTK Codex across 7 industries
      </p>
      <div className="marquee relative overflow-hidden [mask-image:linear-gradient(90deg,transparent,black_10%,black_90%,transparent)]">
        <div className="marquee-track gap-12 pr-12">
          {row.map((p, i) => (
            <span key={i} className="flex shrink-0 items-center gap-3 text-fg-muted" aria-hidden={i >= products.length}>
              <span className="size-3 rounded-[4px]" style={{ background: p.accent }} />
              <span className="font-display text-xl font-bold tracking-tight">{p.name}</span>
              <span className="text-xs text-fg-subtle">{p.cloud}</span>
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
