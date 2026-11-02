import type { Metadata } from 'next';
import { pageMeta } from '@/lib/seo';
import { GraduationCap, Laptop, Rocket, Users } from 'lucide-react';
import { site } from '@/data/site';
import PageHeader from '@/components/ui/PageHeader';
import { Button, SectionHeading } from '@/components/ui/primitives';
import Reveal from '@/components/ui/Reveal';

export const metadata: Metadata = pageMeta({
  title: 'Careers',
  description: 'Join the MTK Codex talent network — remote-first engineering on real production SaaS in Next.js, NestJS, Laravel and React Native.',
  path: '/careers',
  keywords: ['software jobs Lahore', 'remote developer jobs', 'internships'],
});

const perks = [
  { icon: Rocket, title: 'Real production work', text: 'Ship features used by real businesses — not throwaway demos.' },
  { icon: Laptop, title: 'Remote-first', text: 'Work from anywhere with flexible hours and async collaboration.' },
  { icon: GraduationCap, title: 'Learn fast', text: 'Modern stack: Next.js, NestJS, Laravel, React Native, AI and more.' },
  { icon: Users, title: 'Direct mentorship', text: 'Code reviews and pairing with the founder and senior engineers.' },
];

const tracks = ['Full-stack (Next.js / Node)', 'Mobile (React Native)', 'Backend (NestJS / Laravel)', 'UI/UX design', 'QA & automation', 'Internships'];

export default function CareersPage() {
  const mail = `mailto:${site.email}?subject=${encodeURIComponent('Talent network — MTK Codex')}`;
  return (
    <>
      <PageHeader
        eyebrow="Careers"
        title={
          <>
            Build software that <span className="text-gradient">businesses run on.</span>
          </>
        }
        text="We're growing. Join the MTK Codex talent network and be first in line for remote roles, contracts and internships."
      >
        <Button href={mail} external size="lg" arrow>
          Send your CV
        </Button>
      </PageHeader>

      <section className="container-x py-20">
        <SectionHeading eyebrow="Why MTK Codex" title="Grow with a team that ships." />
        <div className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {perks.map((p, i) => (
            <Reveal key={p.title} delay={i * 80}>
              <div className="card spotlight h-full p-6">
                <p.icon className="size-6 text-accent" />
                <h3 className="mt-4 text-lg font-bold">{p.title}</h3>
                <p className="mt-2 text-sm text-fg-muted">{p.text}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="container-x pb-24">
        <div className="night rounded-[28px] p-8 sm:p-12">
          <h2 className="text-3xl font-bold">Talent network tracks</h2>
          <p className="mt-3 max-w-2xl text-white/70">
            There are no open full-time positions listed right now. Email your CV and portfolio with the track you&apos;re interested in, and we&apos;ll
            reach out when a matching role opens.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            {tracks.map((t) => (
              <span key={t} className="rounded-full border border-white/15 bg-white/5 px-4 py-2 text-sm">
                {t}
              </span>
            ))}
          </div>
          <Button href={mail} external size="lg" arrow className="mt-10">
            Join the talent network
          </Button>
        </div>
      </section>
    </>
  );
}
