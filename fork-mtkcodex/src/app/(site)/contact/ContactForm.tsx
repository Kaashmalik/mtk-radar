'use client';

import { useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { CalendarClock, CheckCircle2, Loader2, Mail, MessageCircle, Phone, Send } from 'lucide-react';
import { services } from '@/data/services';
import { products } from '@/data/products';
import { site } from '@/data/site';

const intents: Record<string, string> = {
  demo: 'Book a product demo',
  quote: 'Get a quote for a custom project',
  call: 'Book a call with the founder',
};

/** Dial codes for the markets we serve most; anyone else types the full +code. */
const DIAL_CODES: { code: string; dial: string; label: string }[] = [
  { code: 'PK', dial: '92', label: 'Pakistan +92' },
  { code: 'US', dial: '1', label: 'United States +1' },
  { code: 'GB', dial: '44', label: 'United Kingdom +44' },
  { code: 'AE', dial: '971', label: 'UAE +971' },
  { code: 'SA', dial: '966', label: 'Saudi Arabia +966' },
  { code: 'CA', dial: '1', label: 'Canada +1' },
  { code: 'AU', dial: '61', label: 'Australia +61' },
  { code: 'DE', dial: '49', label: 'Germany +49' },
  { code: 'QA', dial: '974', label: 'Qatar +974' },
  { code: 'OTHER', dial: '', label: 'Other (type +code)' },
];

/** A sensible default country from the visitor's timezone. */
function guessCountry(timezone: string): string {
  if (timezone === 'Asia/Karachi') return 'PK';
  if (timezone === 'Europe/London') return 'GB';
  if (timezone === 'Asia/Dubai') return 'AE';
  if (timezone === 'Asia/Riyadh') return 'SA';
  if (timezone === 'Asia/Qatar') return 'QA';
  if (timezone.startsWith('Australia/')) return 'AU';
  if (timezone === 'Europe/Berlin') return 'DE';
  if (/^America\/(Toronto|Vancouver|Edmonton|Winnipeg|Halifax|Regina|St_Johns)/.test(timezone)) return 'CA';
  if (timezone.startsWith('America/')) return 'US';
  return 'PK';
}

const PREFERRED: [string, string, React.ComponentType<{ className?: string }>][] = [
  ['email', 'Email', Mail],
  ['whatsapp', 'WhatsApp', MessageCircle],
  ['call', 'Phone / video call', Phone],
];

const BOOKING_URL = process.env.NEXT_PUBLIC_BOOKING_URL || '';

const inputCls =
  'w-full rounded-xl border border-line bg-bg px-4 py-3 text-sm outline-none transition placeholder:text-fg-subtle focus:border-brand focus:ring-4 focus:ring-brand/15';

export default function ContactForm() {
  const params = useSearchParams();
  const [state, setState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');
  const [country, setCountry] = useState('PK');
  const [timezone, setTimezone] = useState('');
  const [preferred, setPreferred] = useState('email');

  // Browser-only: the visitor's own timezone picks the default dial code.
  useEffect(() => {
    try {
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
      setTimezone(tz);
      setCountry(guessCountry(tz));
    } catch {
      // Keep the Pakistan default.
    }
  }, []);

  const presetService = params.get('service') ?? '';
  const presetProduct = params.get('product') ?? '';
  const presetIntent = params.get('intent') ?? '';
  const defaultTopic = presetProduct ? `product:${presetProduct}` : presetService ? `service:${presetService}` : presetIntent === 'demo' ? 'demo' : '';

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const data = Object.fromEntries(new FormData(form)) as Record<string, string>;
    if (data.company_website) return; // honeypot (also checked on the server)
    // Join the dial code and the local number into one international number.
    const raw = (data.phone_local || '').trim();
    const dial = DIAL_CODES.find((c) => c.code === country)?.dial || '';
    data.phone = !raw ? '' : raw.startsWith('+') || raw.startsWith('00') || !dial ? raw : `+${dial}${raw.replace(/^0+/, '')}`;
    delete data.phone_local;
    data.preferred = preferred;
    data.timezone = timezone;
    setState('sending');
    try {
      const res = await fetch('/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (res.ok) {
        setState('sent');
        form.reset();
        return;
      }
      if (res.status === 501) {
        // No email provider configured: hand off to the visitor's mail client.
        const body = `Name: ${data.name}\nEmail: ${data.email}\nCompany: ${data.company || '-'}\nTopic: ${data.topic || '-'}\nBudget: ${data.budget || '-'}\n\n${data.message}`;
        window.location.href = `mailto:${site.email}?subject=${encodeURIComponent(`New enquiry from ${data.name}`)}&body=${encodeURIComponent(body)}`;
        setState('sent');
        return;
      }
      setState('error');
    } catch {
      setState('error');
    }
  }

  if (state === 'sent') {
    return (
      <div className="card flex flex-col items-center p-10 text-center">
        <CheckCircle2 className="size-14 text-accent" />
        <h2 className="mt-4 text-2xl font-bold">Thank you — we&apos;ve got it.</h2>
        <p className="mt-2 max-w-sm text-fg-muted">We&apos;ll get back to you within 12 hours with next steps.</p>
        <button type="button" onClick={() => setState('idle')} className="mt-6 text-sm font-semibold text-brand">
          Send another message
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="card space-y-5 p-6 sm:p-8">
      {intents[presetIntent] && (
        <p className="rounded-xl bg-brand-soft px-4 py-3 text-sm font-medium text-brand">{intents[presetIntent]}</p>
      )}
      <div className="grid gap-5 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">Full name *</span>
          <input name="name" required autoComplete="name" className={inputCls} placeholder="Your name" />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">Work email *</span>
          <input name="email" type="email" required autoComplete="email" className={inputCls} placeholder="you@company.com" />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">Company</span>
          <input name="company" autoComplete="organization" className={inputCls} placeholder="Company name" />
        </label>
        <div className="block">
          <span className="mb-1.5 block text-sm font-medium" id="phone-label">
            Phone / WhatsApp
          </span>
          <div className="flex gap-2">
            <select
              aria-label="Country code"
              value={country}
              onChange={(e) => setCountry(e.target.value)}
              className={`${inputCls} w-[44%] shrink-0 px-2`}
            >
              {DIAL_CODES.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.label}
                </option>
              ))}
            </select>
            <input
              name="phone_local"
              type="tel"
              autoComplete="tel-national"
              aria-labelledby="phone-label"
              className={inputCls}
              placeholder={country === 'OTHER' ? '+49 30 1234567' : country === 'PK' ? '300 1234567' : 'Number'}
            />
          </div>
        </div>
      </div>
      <fieldset>
        <legend className="mb-1.5 block text-sm font-medium">Best way to reach you</legend>
        <div className="flex flex-wrap gap-2">
          {PREFERRED.map(([value, label, Icon]) => (
            <label
              key={value}
              className={`inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-3.5 py-2 text-sm font-medium transition ${
                preferred === value ? 'border-brand bg-brand-soft text-brand' : 'border-line text-fg-muted hover:border-brand/50'
              }`}
            >
              <input type="radio" name="preferred_choice" value={value} checked={preferred === value} onChange={() => setPreferred(value)} className="sr-only" />
              <Icon className="size-4" /> {label}
            </label>
          ))}
        </div>
        {timezone && <p className="mt-1.5 text-xs text-fg-subtle">We will reply during your working hours ({timezone.replace(/_/g, ' ')}).</p>}
      </fieldset>
      <label className="block">
        <span className="mb-1.5 block text-sm font-medium">What can we help with?</span>
        <select name="topic" defaultValue={defaultTopic} className={inputCls}>
          <option value="">Choose a topic</option>
          <option value="demo">Product demo</option>
          <optgroup label="Services">
            {services.map((s) => (
              <option key={s.id} value={`service:${s.id}`}>
                {s.title}
              </option>
            ))}
          </optgroup>
          <optgroup label="Products">
            {products.map((p) => (
              <option key={p.slug} value={`product:${p.slug}`}>
                {p.name}
              </option>
            ))}
          </optgroup>
        </select>
      </label>
      <label className="block">
        <span className="mb-1.5 block text-sm font-medium">Estimated budget</span>
        <select name="budget" defaultValue="" className={inputCls}>
          <option value="">Not sure yet</option>
          <option>Under $1,000</option>
          <option>$1,000 – $5,000</option>
          <option>$5,000 – $15,000</option>
          <option>$15,000+</option>
          <option>Monthly subscription</option>
        </select>
      </label>
      <label className="block">
        <span className="mb-1.5 block text-sm font-medium">Project details *</span>
        <textarea name="message" required rows={5} className={inputCls} placeholder="Tell us about your goals, current system and timeline…" />
      </label>
      <input type="text" name="company_website" tabIndex={-1} autoComplete="off" className="hidden" aria-hidden />
      {state === 'error' && (
        <p className="rounded-xl bg-red-500/10 px-4 py-3 text-sm text-red-600 dark:text-red-400">
          Something went wrong. Please email us directly at {site.email}.
        </p>
      )}
      <button
        type="submit"
        disabled={state === 'sending'}
        className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-full bg-cta font-semibold text-on-cta transition hover:bg-cta-hover disabled:opacity-70"
      >
        {state === 'sending' ? <Loader2 className="size-5 animate-spin" /> : <Send className="size-4" />}
        {state === 'sending' ? 'Sending…' : 'Send message'}
      </button>
      <p className="text-center text-xs text-fg-subtle">We reply within 12 hours. Your details are never shared.</p>
      <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-xs">
        <a href="#live-chat" className="inline-flex items-center gap-1 font-semibold text-brand hover:underline">
          <MessageCircle className="size-3.5" /> Prefer to chat now? Open live chat
        </a>
        {BOOKING_URL && (
          <a href={BOOKING_URL} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-semibold text-brand hover:underline">
            <CalendarClock className="size-3.5" /> Book a video call
          </a>
        )}
      </div>
    </form>
  );
}
