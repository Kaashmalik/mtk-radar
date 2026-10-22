# Automation & Human Control

> One policy, validated by the API, enforced on every gated write.

MTK RADAR can run three ways. The mode is chosen in **Settings → Automation
control** and stored as `settings.automation_policy`. Workers read it at the
start of every sweep, and the API re-checks it on every state-changing call —
so a stale or forged worker cannot bypass a `human` stage.

## Modes

| Mode | Collect | Verify | Script | Render | Approve | Schedule | Retry |
|---|---|---|---|---|---|---|---|
| **Manual** | human | human | human | human | human | human | off |
| **Assisted** (default) | auto | auto | auto | auto | **human** | **human** | auto |
| **Autopilot** | auto | auto | auto | auto | auto | auto | auto |

Any stage can be overridden individually. The resulting mode is shown as
`custom`. **Assisted is the default**: the system does the mechanical work,
while a named person still approves every offer and every post.

## What each stage means

| Stage | Automation may… | Human control means… |
|---|---|---|
| `collect` | poll the source registry and ingest candidates | the collector sweep is skipped |
| `verify` | capture official evidence, extract fields, move to `verified` | evidence is still collected only if a human starts verification; no promotion |
| `script` | generate the deterministic versioned claim script | wait for the Script button / API |
| `render` | render captions + 16:9 / 9:16 from a **redaction-reviewed** capture | wait for a human render command |
| `approve` | approve the offer for video **and** approve each queued post | a named reviewer must click approve |
| `schedule` | create queue entries at the next publish window and schedule them | a named reviewer queues posts |

The publishing worker always uploads **only posts that are already approved
and scheduled**. In every mode, approval is bound to the exact script hash.

## Guardrails (all enforced server-side)

| Guardrail | Default | Effect |
|---|---|---|
| `auto_verify_min_confidence` | `0.0` | minimum offer confidence for unattended verification |
| `auto_verify_max_evidence_age_hours` | `72` | refuses stale official evidence |
| `auto_approve_requires_render` | `true` | no auto-approval without a render from the current script |
| `auto_approve_block_unsafe_commands` | `true` | unsafe command cards force a human review |
| `auto_schedule_platforms` | `["youtube"]` | platforms autopilot may queue |
| `auto_schedule_privacy` | `private` | privacy of auto-queued posts |
| `auto_publish_max_per_day` | `3` | daily cap on unattended approvals (429 past it) |
| `auto_retry` | `true` | exponential-backoff retries for failed uploads |
| `retry_max_attempts` | `3` | retry cap |
| `retry_base_seconds` | `300` | backoff base |

Plus two operator switches:

- **Pause all automation** — immediate global kill switch. Approved posts stay
  queued; a human can still act.
- **Dry-run** — workers report what they would do and change nothing.

## Guarantees that cannot be switched off

1. `verified` needs official, provider-domain-checked evidence and a complete
   extraction.
2. Redaction review of capture footage is always a human attestation.
3. A render may only publish when its script hash equals the approved hash.
4. Every automation action is audited as `automation:<stage>`.
5. Offer expiry, material changes, and corrections auto-pause scheduled posts.

The server also refuses:

- an automation actor on a stage set to `human` (403),
- an actor whose stage does not match the action (e.g. `automation:verify`
  trying to schedule) (403),
- unattended approval before a rendered, reviewed video exists (422),
- unattended approval past the daily budget (429),
- unattended scheduling of an expired/corrected offer, a platform outside
  `auto_schedule_platforms`, or a privacy other than
  `auto_schedule_privacy` (409 — re-checked at scheduling time, not only when
  the worker asks for a slot),
- automation resuming a paused post (403 — resume is always a human decision),
- automation marking an offer `published` directly (403 — publishing is
  recorded from the platform result, never assumed).

Scheduling also re-reads the live offer. A post that was approved yesterday
cannot be scheduled today if the offer has since expired or been demoted.

## API

```text
GET    /automation/policy          policy + summary + presets
PUT    /automation/policy          {"policy": {...}} validated + audited
POST   /automation/preset/{name}   manual | assisted | autopilot
GET    /automation/status          budget, queue, recent automation actions
GET    /automation/next-slot       next publish window (UTC) for a platform
POST   /automation/pause           global kill switch
POST   /automation/resume          resume configured stages, clear dry-run
```

The same policy is available as a normal setting:

```bash
curl -X PUT http://localhost:8000/settings/automation_policy \
  -H 'Content-Type: application/json' \
  -d '{"value": {"mode": "assisted"}}'
```

## Identities and audit

| Actor | Used by | Meaning |
|---|---|---|
| `automation:verify` | verification worker | unattended verification |
| `automation:approve` | batch worker | unattended offer/post approval |
| `automation:schedule` | batch worker | unattended queueing |
| `worker` | collectors / metrics / publishing | mechanical work, never approval |
| `<reviewer name>` | personal reviewer token | a human decision |

`audit_log.actor` is the source of truth. The Settings page shows the last 20
automation actions; `GET /automation/status` returns the same data.

## Operational recommendation

Start with **Assisted**, then move one stage at a time:

1. Keep `approve` and `schedule` human until you have watched several complete
   videos and posts.
2. For the first autopilot runs, set `auto_schedule_privacy=private` and
   `auto_publish_max_per_day=1`.
3. Review `GET /automation/status` daily. A rising `failed` count with a flat
   `scheduled` count means credentials or an offer changed.
4. Keep the kill switch bookmarked. Pausing automation never cancels a live
   post; it only stops unattended advancement.
