"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { clientFetch } from "@/lib/api-client";

/**
 * Schedule the reviewed package on one or more platforms. The API gates
 * everything — approved offer state, render existence/QC, redaction review,
 * idempotency — and reports per platform.
 *
 * G19 (evidence-to-video plan): every target carries its OWN account,
 * render and privacy. A platform is only selectable when an active account
 * is connected, and each privacy list shows only modes that platform can
 * honour (the publishing worker enforces the same matrix before upload).
 *
 * v0.18: operator-configured publish windows (settings.publish_windows,
 * §17) render as quick-picks; the default stays 18:00 PKT when unset.
 */
type RenderOption = {
  id: string;
  preset: string;
  language: string;
  width: number;
  height: number;
  duration_s: string | null;
  status?: string;
  qc_status?: string;
};

type Account = { id: string; platform: string; account_handle: string; status?: string };

type Platform = "youtube" | "facebook" | "instagram" | "tiktok";

/** Mirrors workers/publishing/platforms/*: what each upload path can honour. */
const CAPABILITIES: Record<Platform, {
  label: string;
  nativePreset: "landscape" | "vertical";
  privacy: { value: string; label: string }[];
  note?: string;
}> = {
  youtube: {
    label: "YouTube",
    nativePreset: "landscape",
    privacy: [
      { value: "private", label: "Private (test)" },
      { value: "unlisted", label: "Unlisted" },
      { value: "public", label: "Public" },
    ],
  },
  facebook: {
    label: "Facebook",
    nativePreset: "landscape",
    privacy: [
      { value: "private", label: "Unpublished (test)" },
      { value: "public", label: "Published" },
    ],
  },
  instagram: {
    label: "Instagram",
    nativePreset: "vertical",
    privacy: [{ value: "public", label: "Public (no private mode)" }],
    note: "Instagram's publishing API has no private or draft post — this goes live.",
  },
  tiktok: {
    label: "TikTok",
    nativePreset: "vertical",
    privacy: [
      { value: "private", label: "Only me (SELF_ONLY)" },
      { value: "public", label: "Public (audited app only)" },
    ],
    note: "Public needs a TikTok-audited app (TIKTOK_APP_AUDITED); otherwise it is refused before upload.",
  },
};
const ALL_PLATFORMS = Object.keys(CAPABILITIES) as Platform[];

type Target = { accountId: string; renderId: string; privacy: string };

export default function ScheduleForm({
  offerId,
  renders = [],
}: {
  offerId: string;
  renders?: RenderOption[];
}) {
  const router = useRouter();
  const [platforms, setPlatforms] = useState<Platform[]>([]);
  const [targets, setTargets] = useState<Record<string, Target>>({});
  const [language, setLanguage] = useState("en");
  const [metadataVariant, setMetadataVariant] = useState("default");
  const [coverPath, setCoverPath] = useState("");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountsState, setAccountsState] = useState<"loading" | "ok" | "error">("loading");
  const [allowedLanguages, setAllowedLanguages] = useState<string[]>(["en"]);
  const [windows, setWindows] = useState<string[]>([]);
  const [when, setWhen] = useState(() => defaultWhen("18:00"));
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [perPlatform, setPerPlatform] = useState<Record<string, { ok: boolean; text: string }> | null>(null);

  useEffect(() => {
    let alive = true;
    clientFetch("/settings/publish_windows")
      .then((r) => (r.ok ? r.json() : null))
      .then((b) => {
        const list = b?.value?.windows;
        if (alive && Array.isArray(list) && list.length > 0) setWindows(list);
      })
      .catch(() => {}); // settings are an enhancement — the form works without them

    clientFetch("/platform-accounts")
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((list) => {
        if (!alive) return;
        setAccounts(Array.isArray(list) ? list : []);
        setAccountsState("ok");
      })
      .catch(() => alive && setAccountsState("error"));

    // English is always available; Urdu only appears after the operator
    // enables it in Settings → Language policy.
    clientFetch("/settings/language_policy")
      .then((r) => (r.ok ? r.json() : null))
      .then((b) => {
        const list = b?.value?.narration_languages;
        if (alive && Array.isArray(list) && list.length > 0) {
          setAllowedLanguages(list);
          setLanguage((current) => (list.includes(current) ? current : list[0]));
        }
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const activeAccounts = useMemo(() => {
    const by: Record<string, Account[]> = {};
    for (const account of accounts) {
      if ((account.status ?? "active") !== "active") continue;
      (by[account.platform] ??= []).push(account);
    }
    return by;
  }, [accounts]);

  const passedRenders = renders.filter(
    (render) =>
      render.language === language &&
      (render.status ?? "rendered") === "rendered" &&
      render.qc_status === "passed",
  );

  /** Why a platform cannot be targeted right now, or null when it can. */
  function blockedReason(platform: Platform): string | null {
    if (accountsState === "loading") return "checking connected accounts…";
    if (accountsState === "error") return null; // unknown: let the API gate decide
    if (!activeAccounts[platform]?.length) return "no active account — connect it in Connections";
    return null;
  }

  function togglePlatform(platform: Platform) {
    setPerPlatform(null);
    setPlatforms((prev) => {
      if (prev.includes(platform)) return prev.filter((p) => p !== platform);
      return [...prev, platform];
    });
    setTargets((prev) => prev[platform] ? prev : {
      ...prev,
      [platform]: {
        accountId: activeAccounts[platform]?.length === 1 ? activeAccounts[platform][0].id : "",
        renderId: "",
        privacy: CAPABILITIES[platform].privacy[0].value,
      },
    });
  }

  function setTarget(platform: Platform, patch: Partial<Target>) {
    setTargets((prev) => ({ ...prev, [platform]: { ...prev[platform], ...patch } }));
  }

  async function schedule() {
    if (platforms.length === 0) return;
    setBusy(true);
    setError(null);
    setMsg(null);
    setPerPlatform(null);
    const shared = {
      local_time: `${when}:00+05:00`,
      timezone: "Asia/Karachi",
      language,
      metadata_variant: metadataVariant,
      ...(coverPath.trim() ? { cover_path: coverPath.trim() } : {}),
    };
    const pin = (platform: Platform) => {
      const target = targets[platform];
      return {
        privacy: target.privacy,
        ...(target.accountId ? { platform_account_id: target.accountId } : {}),
        ...(target.renderId ? { render_id: target.renderId } : {}),
      };
    };
    try {
      // Single platform keeps the original single endpoint (identical gates).
      if (platforms.length === 1) {
        const platform = platforms[0];
        const res = await clientFetch(`/offers/${offerId}/schedules`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...shared, platform, ...pin(platform) }),
        });
        const body = await res.json().catch(() => ({}));
        if (!res.ok) {
          setError(body.detail ?? `HTTP ${res.status}`);
          return;
        }
        setMsg(
          body.created
            ? `Queued (${body.state}) — approve it on the calendar before it can publish`
            : `Already queued (${body.state}) — idempotent re-submit`,
        );
        router.refresh();
        return;
      }
      // Multi-platform: ONE request; account/render/privacy pinned PER
      // platform so no target ever inherits another platform's account.
      const res = await clientFetch(`/offers/${offerId}/schedules/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...shared,
          privacy: targets[platforms[0]].privacy,
          platforms,
          per_platform: Object.fromEntries(platforms.map((p) => [p, pin(p)])),
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.detail ?? `HTTP ${res.status}`);
        return;
      }
      setPerPlatform(
        Object.fromEntries((body.results ?? []).map(
          (r: { platform: string; ok: boolean; state?: string; detail?: string }) => [
            r.platform,
            { ok: r.ok, text: r.ok ? `queued (${r.state ?? "draft"})` : (r.detail ?? "refused") },
          ],
        )),
      );
      setMsg(
        body.ok
          ? `Queued on ${body.created} platform(s) — approve on the calendar`
          : `Partially queued (${body.created}/${body.requested}) — per-platform results below`,
      );
      router.refresh();
    } catch {
      setError("API unreachable — nothing was scheduled");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="schedule-form">
      <div className="schedule-shared">
        <select
          value={language}
          onChange={(e) => {
            setLanguage(e.target.value);
            setTargets((prev) => Object.fromEntries(
              Object.entries(prev).map(([p, t]) => [p, { ...t, renderId: "" }]),
            ));
          }}
          aria-label="Language"
        >
          {allowedLanguages.map((code) => (
            <option key={code} value={code}>
              {code === "ur" ? "اردو (Urdu voiceover)" : "English"}
            </option>
          ))}
        </select>
        <select
          value={metadataVariant}
          onChange={(e) => setMetadataVariant(e.target.value)}
          aria-label="Metadata variant"
        >
          <option value="default">Packaging A</option>
          <option value="b">Packaging B</option>
        </select>
        <input
          type="datetime-local"
          value={when}
          onChange={(e) => setWhen(e.target.value)}
          aria-label="Publish time (Pakistan time)"
        />
        <input
          value={coverPath}
          onChange={(e) => setCoverPath(e.target.value)}
          placeholder="cover path (optional)"
          aria-label="Cover path"
        />
      </div>

      {windows.length > 0 && (
        <div className="schedule-windows">
          <span className="muted small">Publish windows</span>
          {windows.map((w) => (
            <button key={w} type="button" className="chip-btn" onClick={() => setWhen(defaultWhen(w))}>
              {w}
            </button>
          ))}
        </div>
      )}

      {accountsState === "error" && (
        <p className="notice small" role="status">
          Connected accounts could not be loaded — targets stay selectable and the
          API will refuse any platform without a usable account.
        </p>
      )}

      <div className="schedule-targets" role="group" aria-label="Target platforms">
        {ALL_PLATFORMS.map((platform) => {
          const cap = CAPABILITIES[platform];
          const reason = blockedReason(platform);
          const selected = platforms.includes(platform);
          const target = targets[platform];
          const outcome = perPlatform?.[platform];
          return (
            <div
              key={platform}
              className="schedule-target"
              data-selected={selected || undefined}
              data-blocked={reason ? true : undefined}
            >
              <label className="schedule-target-head">
                <input
                  type="checkbox"
                  checked={selected}
                  disabled={Boolean(reason) && !selected}
                  onChange={() => togglePlatform(platform)}
                />
                <strong>{cap.label}</strong>
                {reason && <span className="muted small">{reason}</span>}
                {outcome && (
                  <span className={`small ${outcome.ok ? "tag tag-ok" : "tag tag-warn"}`}>
                    {outcome.text}
                  </span>
                )}
              </label>
              {selected && target && (
                <div className="schedule-target-body">
                  {(activeAccounts[platform]?.length ?? 0) > 0 && (
                    <select
                      value={target.accountId}
                      onChange={(e) => setTarget(platform, { accountId: e.target.value })}
                      aria-label={`${cap.label} account`}
                    >
                      {activeAccounts[platform].length > 1 && (
                        <option value="">Choose account…</option>
                      )}
                      {activeAccounts[platform].map((account) => (
                        <option key={account.id} value={account.id}>{account.account_handle}</option>
                      ))}
                    </select>
                  )}
                  <select
                    value={target.renderId}
                    onChange={(e) => setTarget(platform, { renderId: e.target.value })}
                    aria-label={`${cap.label} render`}
                    title="Pin the exact QC-passed file. Auto uses the platform's native aspect."
                  >
                    <option value="">
                      Auto: {cap.nativePreset === "vertical" ? "9:16 vertical" : "16:9 landscape"}
                    </option>
                    {passedRenders.map((render) => (
                      <option key={render.id} value={render.id}>
                        {render.preset} · {render.width}×{render.height}
                        {render.duration_s ? ` · ${Number(render.duration_s).toFixed(0)}s` : ""}
                        {render.preset !== cap.nativePreset ? " (non-native aspect)" : ""}
                      </option>
                    ))}
                  </select>
                  <select
                    value={target.privacy}
                    onChange={(e) => setTarget(platform, { privacy: e.target.value })}
                    aria-label={`${cap.label} privacy`}
                  >
                    {cap.privacy.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                  {cap.note && <p className="muted small schedule-note">{cap.note}</p>}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="schedule-actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy || platforms.length === 0 || platforms.some(
            (p) => (activeAccounts[p]?.length ?? 0) > 1 && !targets[p]?.accountId,
          )}
          onClick={schedule}
        >
          {busy ? "Scheduling…"
            : platforms.length === 0 ? "Select a platform"
              : platforms.length > 1 ? `Schedule on ${platforms.length} platforms`
                : `Schedule on ${CAPABILITIES[platforms[0]].label}`}
        </button>
        {msg && <span className="small" style={{ color: "var(--ok)" }}>{msg}</span>}
        {error && <span className="small" role="alert" style={{ color: "var(--danger)" }}>{error}</span>}
      </div>
    </div>
  );
}

/** `when` values are PKT wall-clock (the submit appends +05:00). */
function defaultWhen(hhmm: string): string {
  const [hh, mm] = hhmm.split(":").map(Number);
  const pad = (x: number) => String(x).padStart(2, "0");
  const d = new Date(Date.now() + 24 * 3600 * 1000);
  // shift into Asia/Karachi wall-clock so the pre-filled slot matches the window
  const pkt = new Date(d.toLocaleString("en-US", { timeZone: "Asia/Karachi" }));
  pkt.setHours(hh, mm, 0, 0);
  return `${pkt.getFullYear()}-${pad(pkt.getMonth() + 1)}-${pad(pkt.getDate())}T${pad(pkt.getHours())}:${pad(pkt.getMinutes())}`;
}
