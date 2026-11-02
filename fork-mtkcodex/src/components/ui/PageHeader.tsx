export default function PageHeader({
  eyebrow,
  title,
  text,
  children,
}: {
  eyebrow: string;
  title: React.ReactNode;
  text?: string;
  children?: React.ReactNode;
}) {
  return (
    <section className="relative isolate overflow-hidden bg-[linear-gradient(180deg,var(--hero-from),var(--hero-to))]">
      <div className="bg-grid absolute inset-0 -z-10 [mask-image:radial-gradient(ellipse_at_top,black,transparent_70%)]" />
      <div className="glow -z-10 left-[10%] top-[-40%] size-[420px] bg-[#14a89a] opacity-35" />
      <div className="glow -z-10 right-[5%] top-[-30%] size-[360px] bg-[#62d84e] opacity-25" />
      <div className="container-x py-20 text-center sm:py-24">
        <p className="eyebrow">{eyebrow}</p>
        <h1 className="mx-auto mt-4 max-w-4xl text-4xl font-extrabold leading-[1.05] sm:text-6xl">{title}</h1>
        {text && <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-fg-muted">{text}</p>}
        {children && <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">{children}</div>}
      </div>
    </section>
  );
}
