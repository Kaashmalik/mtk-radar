# First Offer Recipe — Pilot Case Study (Weeks 5–6 Exit)

Per the master plan (§13, §18): build **one complete case study** end-to-end before expanding sources — a current, officially documented developer/student offer with explicit eligibility. The recommended pilot: a **.TECH domain offer through a student-benefit program** (GitHub Student Developer Pack partner).

Exit criterion: *one eligible claim recorded and reviewed without leaking secrets.*

---

## Phase 0 — Pre-flight (before anything is filmed)

- [ ] Offer exists in the system: inbox item → review desk → state **verified**
- [ ] Official sources registered + evidence snapshots captured (`.TECH` partner page, student-program listing, terms)
- [ ] Eligibility confirmed for the **operator's own account** (country, enrollment, verification docs ready)
- [ ] Recorded facts pinned: promo code, redemption URL, expiry, **renewal price + auto-renew setting**
- [ ] If the operator is NOT eligible: use a clearly labeled demo account or a consenting eligible participant — **never simulate a successful redemption**

## Phase 1 — Script & checklist

- [ ] Review desk → offer page → **Generate script** (blocked unless verified — by design)
- [ ] Review the generated checklist top-to-bottom; edit the offer record, not the markdown, if facts are wrong (material edits auto-revert the offer for re-verification)
- [ ] Command cards: every command has an official `source_url` + tested `expected_output`; unsafe cards are flagged — fix before filming
- [ ] If commands only apply AFTER the claim (e.g., DNS verification), narrative must say so — do not imply deployment is part of redemption (§15)

## Phase 2 — Capture day

```bash
pip install -r workers/capture/requirements.txt
python -m playwright install chromium
python workers/capture/main.py --offer <OFFER_ID> --api http://localhost:8000
```

- [ ] Clean laptop profile; close unrelated tabs; no personal browsing
- [ ] Follow the guided steps: automation opens pages + records 1280x720 + keeps the step log; **you perform every account action**
- [ ] Pause on irreversible/paid decisions and say what is happening (§4)
- [ ] Show the **renewal price + auto-renew UI** before finalizing
- [ ] Show the verification checkpoint: where the benefit appears in the account

## Phase 3 — Redaction review (release-blocking)

- [ ] Worker posts the session; server scans the step log for secret patterns (findings report pattern+count only — values never leave the machine)
- [ ] Manually re-check: recording, audio narration, terminal history, captions/manifest
- [ ] Attest via `POST /captures/{id}/redaction-review` (reviewer + note) — renders and publishing must require `redaction_reviewed=true`

## Phase 4 — Post-capture

- [ ] Produce 16:9 master + 9:16 vertical (weeks 7-8 pipeline)
- [ ] Private/unlisted test upload; **recheck offer validity once more before it would ever go public**
- [ ] Log measured numbers: time spent, missed details, corrections, rendering reliability — this calibration decides what gets automated next

## Hard no's (§4, §11)

- ❌ Staged success screens or implied universal results
- ❌ API keys, passwords, recovery codes, personal data in footage/transcript/project
- ❌ Showing a promo code that isn't verified as authorized for redistribution
- ❌ Simulating eligibility you don't have
