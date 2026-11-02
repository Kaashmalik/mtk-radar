/**
 * MTK Radar AI's automation pipeline, as documented in the mtk-radar repo
 * (docs/automation-and-human-control.md). Keep in sync when the policy changes.
 */

export type FlowMode = 'manual' | 'assisted' | 'autopilot';

/** How a stage runs: by policy, or fixed regardless of mode. */
export type StageControl = 'policy' | 'always-human' | 'always-auto';

export type FlowStage = {
  id: string;
  /** Policy key in `settings.automation_policy`; absent for fixed stages. */
  policyKey?: 'collect' | 'verify' | 'script' | 'render' | 'approve' | 'schedule';
  control: StageControl;
  title: string;
  worker: string;
  /** Offer lifecycle state once this stage succeeds. */
  lifecycle: string;
  auto: string;
  human: string;
  guarantee?: string;
};

export const FLOW_MODES: { id: FlowMode; label: string; summary: string }[] = [
  { id: 'manual', label: 'Manual', summary: 'A person triggers every step. Nothing advances on its own.' },
  {
    id: 'assisted',
    label: 'Assisted',
    summary: 'Default. Machines collect, verify, script and render; a named reviewer approves and schedules every post.',
  },
  {
    id: 'autopilot',
    label: 'Autopilot',
    summary: 'Every stage runs unattended inside server-side guardrails, with a daily cap and a kill switch.',
  },
];

/** Which policy stages are automatic in each preset (from the repo's mode matrix). */
export const MODE_MATRIX: Record<FlowMode, Record<NonNullable<FlowStage['policyKey']>, boolean>> = {
  manual: { collect: false, verify: false, script: false, render: false, approve: false, schedule: false },
  assisted: { collect: true, verify: true, script: true, render: true, approve: false, schedule: false },
  autopilot: { collect: true, verify: true, script: true, render: true, approve: true, schedule: true },
};

export const FLOW_STAGES: FlowStage[] = [
  {
    id: 'discover',
    policyKey: 'collect',
    control: 'policy',
    title: 'Discover',
    worker: 'workers/collectors',
    lifecycle: 'Candidate',
    auto: 'Polls the source registry — RSS/Atom, GitHub releases, official-page watch — plus trend signals from Hacker News, Reddit, Hugging Face papers, star velocity and Google Trends. Deduplicates by canonical URL.',
    human: 'Choose source categories, regions and trust tiers. Save any page with the Chrome extension.',
    guarantee: 'Social posts only create leads (Tier B); coupon sites and leaked codes are excluded (Tier C).',
  },
  {
    id: 'verify',
    policyKey: 'verify',
    control: 'policy',
    title: 'Verify',
    worker: 'workers/verification',
    lifecycle: 'Verified',
    auto: 'Captures an immutable evidence snapshot (URL, time, publisher, excerpt, content hash), extracts eligibility, region, expiry and claim steps, and flags conflicts between sources.',
    human: 'Approve, reject or request more evidence; resolve conflicting terms.',
    guarantee: '“Verified” always needs official, provider-domain-checked evidence. The AI extracts — it is never the source.',
  },
  {
    id: 'script',
    policyKey: 'script',
    control: 'policy',
    title: 'Script',
    worker: 'workers/batch',
    lifecycle: 'Verified',
    auto: 'Generates a deterministic, versioned claim script with command cards, a shot list, storyboard and platform copy. English by default; Urdu voiceover is opt-in.',
    human: 'Edit factual claims and narration in the Studio before anything is recorded.',
  },
  {
    id: 'capture',
    control: 'always-human',
    title: 'Capture',
    worker: 'workers/capture',
    lifecycle: 'Verified',
    auto: 'Records the real claim flow in a Playwright session, through a validating egress proxy, with local redaction helpers.',
    human: 'A person operates the session and signs off the redaction review.',
    guarantee: 'Redaction review is always a human attestation — no secrets ever reach the video.',
  },
  {
    id: 'render',
    policyKey: 'render',
    control: 'policy',
    title: 'Render & QC',
    worker: 'workers/render',
    lifecycle: 'Verified',
    auto: 'FFmpeg renders 16:9 and 9:16 cuts with captions from the capture log and narration, then measures a full decode, black/freeze/silence, loudness and caption safe areas.',
    human: 'Trigger a render manually, or review flagged QC results.',
    guarantee: 'Only a render that passed measured QC can be scheduled or published.',
  },
  {
    id: 'approve',
    policyKey: 'approve',
    control: 'policy',
    title: 'Approve',
    worker: 'workers/batch',
    lifecycle: 'Approved for video',
    auto: 'Approves the offer and each queued post inside guardrails: fresh render, safe commands, under the daily cap.',
    human: 'A named reviewer clicks approve — by default this stage stays human.',
    guarantee: 'Approval is bound to the exact script hash; any change needs re-approval.',
  },
  {
    id: 'schedule',
    policyKey: 'schedule',
    control: 'policy',
    title: 'Schedule',
    worker: 'workers/batch',
    lifecycle: 'Approved for video',
    auto: 'Builds platform-specific packages and queues them at the next publish window for each platform.',
    human: 'Queue, reschedule, pause or cancel any post from the calendar.',
    guarantee: 'Scheduling re-reads the live offer: an expired or demoted offer cannot be queued.',
  },
  {
    id: 'publish',
    control: 'always-auto',
    title: 'Publish',
    worker: 'workers/publishing',
    lifecycle: 'Published',
    auto: 'Uploads through the official YouTube Data, Meta Graph, Instagram Graph and TikTok Content Posting APIs, with backoff retries and a circuit breaker.',
    human: 'Nothing to do — but only posts that are already approved and scheduled are ever uploaded.',
    guarantee: '“Published” is recorded from the platform’s response, never assumed.',
  },
  {
    id: 'learn',
    control: 'always-auto',
    title: 'Learn & monitor',
    worker: 'workers/metrics · workers/monitor',
    lifecycle: 'Expired / Corrected',
    auto: 'Pulls audience metrics, watches offer expiry, token health and page freshness, and sends alerts.',
    human: 'Record corrections, request takedowns or refresh stale offers.',
    guarantee: 'Expiry, material changes and corrections automatically pause scheduled posts.',
  },
];

export const LIFECYCLE = ['Candidate', 'Evidence needed', 'Verified', 'Approved for video', 'Published', 'Expired / Corrected'];

export const GUARDRAILS: { value: string; label: string }[] = [
  { value: '72 h', label: 'Maximum age of official evidence for unattended verification' },
  { value: '3 / day', label: 'Cap on unattended approvals (the API answers 429 past it)' },
  { value: 'Private', label: 'Default privacy for posts queued by autopilot' },
  { value: 'YouTube', label: 'Platforms autopilot may queue, until you allow more' },
  { value: '3×', label: 'Upload retries with exponential backoff from 5 minutes' },
  { value: 'Render first', label: 'No unattended approval without a reviewed render of the current script' },
];

export const GUARANTEES = [
  'Verified status needs official, domain-checked evidence and a complete extraction.',
  'Redaction review of capture footage is always a human attestation.',
  'A render can publish only when its script hash matches the approved hash.',
  'Every unattended action is audited as automation:<stage>.',
  'Expiry, material changes and corrections auto-pause queued posts.',
];

export const PUBLISH_PLATFORMS = ['YouTube', 'Facebook', 'Instagram', 'TikTok'];
