const items = [
  "Simple suits",
  "Designer cuts",
  "Party wear",
  "Maxi & frocks",
  "Bridal & formal",
  "Alterations",
  "Home measurement",
  "48-hour express",
];

export function Marquee() {
  return (
    <div className="overflow-hidden border-y border-plum/10 bg-plum py-5 text-ivory" aria-hidden>
      <div className="flex w-max animate-marquee gap-12 whitespace-nowrap">
        {[...items, ...items].map((item, i) => (
          <span key={i} className="font-display flex items-center gap-12 text-2xl italic">
            {item}
            <svg viewBox="0 0 24 24" className="size-4 text-gold" fill="currentColor">
              <path d="M12 0l2.5 9.5L24 12l-9.5 2.5L12 24l-2.5-9.5L0 12l9.5-2.5z" />
            </svg>
          </span>
        ))}
      </div>
    </div>
  );
}
