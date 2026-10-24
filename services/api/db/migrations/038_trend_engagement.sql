-- EP-02 G08: momentum comes from observed engagement.
--
-- trend_candidates.velocity used to be BOTH the momentum input (score/hour
-- bumping demand) and a display metric — but internal score movement mixes
-- freshness and keyword facets, so a keyword-rich retitle could fake a
-- rising trend. Scoring now derives momentum ONLY from engagement growth
-- observed at the source (source_observations measurements, migration 037);
-- `velocity` remains as a recorded score-history diagnostic.
--
-- `engagement` records the measured rate so the number on the radar can be
-- recomputed and audited: {"known":, "metric":, "per_h":, "window_h":,
-- "delta":, "reason":}.

ALTER TABLE trend_candidates
  ADD COLUMN IF NOT EXISTS engagement JSONB NOT NULL DEFAULT '{}';
