import Link from 'next/link';
import { ArrowRight } from 'lucide-react';

type ButtonProps = {
  href: string;
  children: React.ReactNode;
  variant?: 'primary' | 'secondary' | 'ghost';
  size?: 'md' | 'lg';
  external?: boolean;
  arrow?: boolean;
  className?: string;
};

const variants = {
  primary:
    'bg-cta text-on-cta shadow-[0_8px_24px_-10px_var(--cta)] hover:bg-cta-hover hover:shadow-[0_12px_32px_-8px_var(--cta)]',
  secondary: 'border border-line-strong bg-elevated text-fg hover:border-brand hover:text-brand',
  ghost: 'text-brand hover:bg-brand-soft',
};

export function Button({ href, children, variant = 'primary', size = 'md', external, arrow, className = '' }: ButtonProps) {
  const cls = `group inline-flex items-center justify-center gap-2 rounded-full font-semibold transition-all duration-200 ${
    size === 'lg' ? 'h-12 px-6 text-[15px]' : 'h-10 px-5 text-sm'
  } ${variants[variant]} ${className}`;
  const content = (
    <>
      {children}
      {arrow && <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" aria-hidden />}
    </>
  );
  if (external) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className={cls}>
        {content}
      </a>
    );
  }
  return (
    <Link href={href} className={cls}>
      {content}
    </Link>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  text,
  align = 'center',
}: {
  eyebrow?: string;
  title: React.ReactNode;
  text?: string;
  align?: 'center' | 'left';
}) {
  return (
    <div className={`max-w-3xl ${align === 'center' ? 'mx-auto text-center' : ''}`}>
      {eyebrow && <p className="eyebrow mb-4">{eyebrow}</p>}
      <h2 className="text-3xl font-bold leading-[1.1] sm:text-4xl lg:text-5xl">{title}</h2>
      {text && <p className="mt-5 text-base leading-relaxed text-fg-muted sm:text-lg">{text}</p>}
    </div>
  );
}

export function StatusBadge({ status }: { status: 'Live' | 'Beta' | 'Available' }) {
  const color = status === 'Live' ? '#22c55e' : status === 'Beta' ? '#f59e0b' : '#6b82ff';
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-0.5 text-[11px] font-semibold text-fg-muted">
      <span className="pulse-dot size-1.5 rounded-full" style={{ background: color, color }} />
      {status}
    </span>
  );
}

export function Logo({ className = '' }: { className?: string }) {
  return (
    <span className={`inline-flex shrink-0 items-center gap-2.5 whitespace-nowrap ${className}`}>
      <svg viewBox="0 0 40 40" className="size-9" aria-hidden>
        <defs>
          <linearGradient id="mtk-logo" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#62d84e" />
            <stop offset="0.55" stopColor="#14a89a" />
            <stop offset="1" stopColor="#0b4f6c" />
          </linearGradient>
        </defs>
        <rect width="40" height="40" rx="11" fill="url(#mtk-logo)" />
        <path d="M14 13 L8 20 L14 27" stroke="#fff" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M26 13 L32 20 L26 27" stroke="#fff" strokeWidth="3" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M22.5 11 L17.5 29" stroke="#fff" strokeWidth="3" strokeLinecap="round" opacity="0.85" />
      </svg>
      <span className="font-display text-lg font-bold tracking-tight">
        MTK <span className="text-gradient">Codex</span>
      </span>
    </span>
  );
}
