/**
 * Offer lifecycle state machine — master plan §3.
 * Candidate → Evidence needed → Verified → Approved for video → Published → Expired/Corrected
 *
 * HARD RULE: video generation and scheduling are blocked before `verified`,
 * and schedules auto-pause when an offer expires or changes.
 */

export const OFFER_STATES = [
  "candidate",
  "evidence_needed",
  "verified",
  "approved_for_video",
  "published",
  "expired",
  "corrected",
] as const;

export type OfferState = (typeof OFFER_STATES)[number];

export const TRANSITIONS: Record<OfferState, OfferState[]> = {
  candidate: ["evidence_needed", "expired"],
  evidence_needed: ["candidate", "verified", "expired"],
  verified: ["approved_for_video", "evidence_needed", "expired", "corrected"],
  approved_for_video: ["published", "verified", "expired", "corrected"],
  published: ["expired", "corrected"],
  expired: ["evidence_needed"],
  corrected: ["evidence_needed", "verified"],
};

export function canTransition(from: OfferState, to: OfferState): boolean {
  return TRANSITIONS[from]?.includes(to) ?? false;
}

export function canGenerateVideo(state: OfferState): boolean {
  // Blocked from Candidate or Evidence needed (master plan §3).
  return state === "verified" || state === "approved_for_video" || state === "published";
}

export function canSchedule(state: OfferState, recheckAt: Date, expiresAt?: Date | null): boolean {
  return (
    state === "approved_for_video" &&
    recheckAt.getTime() <= Date.now() &&
    (!expiresAt || expiresAt.getTime() > Date.now())
  );
}
