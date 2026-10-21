"use client";

/** Reviewer identity (v0.16) — personal API tokens minted server-side with
 * `python -m scripts.mint_reviewer --name <name>`. The token authenticates
 * THIS reviewer (`Authorization: Bearer …`); the API binds audit/reviewer
 * fields to it server-side. The shared worker token never reaches the
 * browser. No tokens live in build-time env: identity is per-operator,
 * stored in localStorage. */

const TOKEN_KEY = "mtk-reviewer-token";
const NAME_KEY = "mtk-reviewer-name";

export function getReviewerToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function getReviewerName(): string {
  if (typeof window === "undefined") return "operator";
  return window.localStorage.getItem(NAME_KEY) ?? "operator";
}

export function setReviewerIdentity(name: string, token: string): void {
  window.localStorage.setItem(NAME_KEY, name);
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearReviewerIdentity(): void {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(NAME_KEY);
}
