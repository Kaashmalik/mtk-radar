'use client';

import { useEffect, useState } from 'react';
import {
  Bot,
  CalendarClock,
  CheckCircle2,
  Clapperboard,
  FileText,
  Hand,
  LineChart,
  Lock,
  PauseCircle,
  Radar,
  ScanSearch,
  Send,
  ShieldCheck,
  TestTube2,
  Video,
} from 'lucide-react';
import {
  FLOW_MODES,
  FLOW_STAGES,
  GUARANTEES,
  GUARDRAILS,
  LIFECYCLE,
  MODE_MATRIX,
  PUBLISH_PLATFORMS,
  type FlowMode,
  type FlowStage,
} from '@/data/radar-flow';
import { prefersReducedMotion } from '@/components/motion/useInView';

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  discover: Radar,
  verify: ScanSearch,
  script: FileText,
  capture: Video,
  render: Clapperboard,
  approve: CheckCircle2,
  schedule: CalendarClock,
  publish: Send,
  learn: LineChart,
};

type Runner = 'auto' | 'human' | 'always-human' | 'always-auto';

function runnerFor(stage: FlowStage, mode: FlowMode): Runner {
  if (stage.control === 'always-human') return 'always-human';
  if (stage.control === 'always-auto') return 'always-auto';
  return stage.policyKey && MODE_MATRIX[mode][stage.policyKey] ? 'auto' : 'human';
}

const RUNNER_LABEL: Record<Runner, string> = {
  auto: 'Automatic',
  human: 'Human approves',
  'always-human': 'Always human',
  'always-auto': 'Automatic · approved posts only',
};

function RunnerBadge({ runner }: { runner: Runner }) {
  const automatic = runner === 'auto' || runner === 'always-auto';
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
        automatic
          ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400'
          : 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400'
      }`}
    >
      {automatic ? <Bot className="size-3" /> : runner === 'always-human' ? <Lock className="size-3" /> : <Hand className="size-3" />}
      {RUNNER_LABEL[runner]}
    </span>
  );
}

/**
 * Interactive walkthrough of MTK Radar AI's pipeline: pick a mode to see which
 * stages run unattended, and follow an offer from discovery to publishing.
 */
export default function AutomationFlow({ accent = '#f97316' }: { accent?: string }) {
  const [mode, setMode] = useState<FlowMode>('assisted');
  const [active, setActive] = useState(0);
  const [selected, setSelected] = useState(0);
  const [playing, setPlaying] = useState(true);

  // Walk an offer through the stages. Stops for reduced-motion users and once someone picks a stage.
  useEffect(() => {
    if (!playing || prefersReducedMotion()) return;
    const timer = window.setInterval(() => setActive((i) => (i + 1) % FLOW_STAGES.length), 1800);
    return () => window.clearInterval(timer);
  }, [playing]);

  const focus = playing ? active : selected;
  const stage = FLOW_STAGES[focus];
  const StageIcon = ICONS[stage.id] || Radar;
  const autoCount = FLOW_STAGES.filter((s) => {
    const r = runnerFor(s, mode);
    return r === 'auto' || r === 'always-auto';
  }).length;

  return (
    <section id="automation-flow" className="container-x scroll-mt-24 pb-16" aria-labelledby="automation-flow-title">
      <p className="eyebrow" style={{ color: accent }}>
        Automation flow
      </p>
      <div className="mt-3 flex flex-wrap items-end justify-between gap-6">
        <div className="max-w-2xl">
          <h2 id="automation-flow-title" className="text-3xl font-bold sm:text-4xl">
            From an official page to a published video — automatically, with a human in control.
          </h2>
          <p className="mt-3 text-fg-muted">
            Nine stages, one automation policy. Switch modes to see what runs on its own, then click any stage for the details.
          </p>
        </div>
        <div className="inline-flex rounded-full border border-line bg-elevated p-1" role="radiogroup" aria-label="Automation mode">
          {FLOW_MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              role="radio"
              aria-checked={mode === m.id}
              onClick={() => setMode(m.id)}
              className={`rounded-full px-4 py-2 text-sm font-semibold transition ${mode === m.id ? 'text-white shadow' : 'text-fg-muted hover:text-fg'}`}
              style={mode === m.id ? { background: accent } : undefined}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <p className="text-fg-muted">{FLOW_MODES.find((m) => m.id === mode)?.summary}</p>
        <p className="font-semibold" style={{ color: accent }}>
          {autoCount} of {FLOW_STAGES.length} stages automatic
        </p>
      </div>

      {/* Offer lifecycle follows the stage the offer is in */}
      <ol className="mt-6 flex flex-wrap items-center gap-1.5 text-[11px] font-semibold" aria-label="Offer lifecycle">
        {LIFECYCLE.map((state, i) => {
          const current = state === stage.lifecycle;
          return (
            <li key={state} className="flex items-center gap-1.5">
              <span
                className={`rounded-full border px-2.5 py-1 transition ${current ? 'text-white' : 'border-line text-fg-subtle'}`}
                style={current ? { background: accent, borderColor: accent } : undefined}
                aria-current={current ? 'step' : undefined}
              >
                {state}
              </span>
              {i < LIFECYCLE.length - 1 && <span className="text-fg-subtle">→</span>}
            </li>
          );
        })}
      </ol>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1.35fr_1fr]">
        <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label="Pipeline stages">
          {FLOW_STAGES.map((s, i) => {
            const Icon = ICONS[s.id] || Radar;
            const runner = runnerFor(s, mode);
            const isFocus = i === focus;
            const done = playing && i < active;
            return (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => {
                    setPlaying(false);
                    setSelected(i);
                  }}
                  aria-pressed={!playing && selected === i}
                  className={`group relative flex h-full w-full flex-col gap-2 rounded-2xl border bg-elevated p-4 text-left transition hover:-translate-y-0.5 ${
                    isFocus ? 'shadow-float' : 'border-line'
                  }`}
                  style={isFocus ? { borderColor: accent, boxShadow: `0 0 0 3px ${accent}26` } : undefined}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span
                      className="grid size-9 place-items-center rounded-xl text-white transition"
                      style={{ background: isFocus || done ? accent : `${accent}99` }}
                    >
                      <Icon className="size-4" />
                    </span>
                    <span className="font-mono text-[10px] text-fg-subtle">{String(i + 1).padStart(2, '0')}</span>
                  </span>
                  <span className="font-bold">{s.title}</span>
                  <RunnerBadge runner={runner} />
                  <span className="truncate font-mono text-[10px] text-fg-subtle">{s.worker}</span>
                  {isFocus && playing && (
                    <span className="absolute right-3 top-3 flex size-2.5" aria-hidden>
                      <span className="absolute inline-flex size-full animate-ping rounded-full opacity-75" style={{ background: accent }} />
                      <span className="relative inline-flex size-2.5 rounded-full" style={{ background: accent }} />
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ol>

        <div className="card flex flex-col p-6" aria-live="polite">
          <div className="flex items-center gap-3">
            <span className="grid size-11 place-items-center rounded-2xl text-white" style={{ background: accent }}>
              <StageIcon className="size-5" />
            </span>
            <div>
              <p className="text-xs font-semibold text-fg-subtle">
                Stage {focus + 1} of {FLOW_STAGES.length}
              </p>
              <h3 className="text-xl font-bold">{stage.title}</h3>
            </div>
          </div>
          <div className="mt-3">
            <RunnerBadge runner={runnerFor(stage, mode)} />
          </div>
          <dl className="mt-5 space-y-4 text-sm">
            <div>
              <dt className="flex items-center gap-1.5 font-semibold">
                <Bot className="size-4 text-emerald-500" /> What the automation does
              </dt>
              <dd className="mt-1 leading-relaxed text-fg-muted">{stage.auto}</dd>
            </div>
            <div>
              <dt className="flex items-center gap-1.5 font-semibold">
                <Hand className="size-4 text-amber-500" /> Human control
              </dt>
              <dd className="mt-1 leading-relaxed text-fg-muted">{stage.human}</dd>
            </div>
            {stage.guarantee && (
              <div className="rounded-xl border border-line bg-muted/40 p-3">
                <dt className="flex items-center gap-1.5 font-semibold">
                  <ShieldCheck className="size-4" style={{ color: accent }} /> Guarantee
                </dt>
                <dd className="mt-1 leading-relaxed text-fg-muted">{stage.guarantee}</dd>
              </div>
            )}
          </dl>
          <div className="mt-auto flex items-center justify-between gap-2 pt-5 text-xs">
            <span className="font-mono text-fg-subtle">{stage.worker}</span>
            <button
              type="button"
              onClick={() => {
                if (!playing) setActive(selected);
                setPlaying((p) => !p);
              }}
              className="inline-flex items-center gap-1 font-semibold"
              style={{ color: accent }}
            >
              {playing ? <PauseCircle className="size-4" /> : <TestTube2 className="size-4" />}
              {playing ? 'Pause walkthrough' : 'Play walkthrough'}
            </button>
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="card p-6 lg:col-span-2">
          <h3 className="flex items-center gap-2 font-bold">
            <ShieldCheck className="size-4" style={{ color: accent }} /> Guardrails, enforced by the API
          </h3>
          <p className="mt-1 text-sm text-fg-muted">
            Workers read the policy on every sweep and the server re-checks it on every gated write, so a stale or forged worker cannot skip a
            human stage.
          </p>
          <dl className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {GUARDRAILS.map((g) => (
              <div key={g.label} className="rounded-xl border border-line p-3">
                <dt className="font-display text-lg font-bold" style={{ color: accent }}>
                  {g.value}
                </dt>
                <dd className="mt-0.5 text-xs leading-relaxed text-fg-muted">{g.label}</dd>
              </div>
            ))}
          </dl>
          <div className="mt-4 flex flex-wrap gap-2 text-xs">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-red-500/30 bg-red-500/10 px-3 py-1 font-semibold text-red-600 dark:text-red-400">
              <PauseCircle className="size-3.5" /> Pause all automation — instant kill switch
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-line px-3 py-1 font-semibold text-fg-muted">
              <TestTube2 className="size-3.5" /> Dry-run — reports what would happen, changes nothing
            </span>
          </div>
        </div>

        <div className="card p-6">
          <h3 className="flex items-center gap-2 font-bold">
            <Lock className="size-4" style={{ color: accent }} /> Cannot be switched off
          </h3>
          <ul className="mt-3 space-y-2.5 text-sm text-fg-muted">
            {GUARANTEES.map((g) => (
              <li key={g} className="flex gap-2">
                <CheckCircle2 className="mt-0.5 size-4 shrink-0" style={{ color: accent }} />
                <span>{g}</span>
              </li>
            ))}
          </ul>
          <p className="mt-5 text-xs font-semibold text-fg-subtle">Publishes to</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {PUBLISH_PLATFORMS.map((p) => (
              <span key={p} className="rounded-full border border-line px-2.5 py-1 text-xs font-semibold">
                {p}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
