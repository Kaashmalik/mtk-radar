import type { CSSProperties } from "react";

/** Shared animated radar scope. Blips are positioned deterministically from
 * the real trend score: hotter leads sit closer to the centre. The sweep and
 * pulse are CSS-only so the component works in a server page and honours
 * prefers-reduced-motion globally. */

export type RadarCandidate = {
  id: string;
  title: string;
  score: number | string;
  status?: string;
  source_provider?: string | null;
};

function pct(value: number): string {
  return `${Math.max(2, Math.min(98, value)).toFixed(1)}%`;
}

export default function RadarScope({
  candidates,
  compact = false,
  label = "Live topic radar",
}: {
  candidates: RadarCandidate[];
  compact?: boolean;
  label?: string;
}) {
  const visible = candidates.slice(0, compact ? 7 : 18);
  return (
    <div className="radar-wrap" style={{ width: "100%" }}>
      <div
        className="radar-scope"
        role="img"
        aria-label={`${label} with ${visible.length} scored leads`}
        style={compact ? ({ "--radar-size": "220px" } as CSSProperties) : undefined}
      >
        {visible.map((candidate, index) => {
          const score = Math.max(0, Math.min(100, Number(candidate.score) || 0));
          const angle = (index * 137.5 + 22) * (Math.PI / 180);
          const radius = 42 - score * 0.32; // 10–42% from centre
          const x = 50 + Math.cos(angle) * radius;
          const y = 50 + Math.sin(angle) * radius;
          const tone = score >= 78 ? "hot" : score >= 55 ? "" : "cool";
          return (
            <span
              key={candidate.id}
              className={`radar-blip ${tone}`}
              style={{
                left: pct(x),
                top: pct(y),
                "--delay": `${(index % 5) * 0.35}s`,
              } as CSSProperties}
              title={`${candidate.title} · ${score.toFixed(1)}`}
            />
          );
        })}
      </div>
      <div className="radar-legend" aria-hidden="true">
        <span><i style={{ background: "var(--danger)" }} />hot ≥ 78</span>
        <span><i style={{ background: "var(--warn)" }} />warm</span>
        <span><i style={{ background: "var(--accent)" }} />watch</span>
      </div>
    </div>
  );
}
