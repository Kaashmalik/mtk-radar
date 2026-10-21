# Upgrade checklist (upstream dependencies & images)

Every upstream we pin is upgraded deliberately, never by a floating tag. This
is the checklist the master plan §8 asks for; it applies to Python packages,
Docker images, and pinned browser binaries.

## Before you touch a pin

- [ ] Read the upstream's **LICENSE at the new version** (licenses change between releases).
- [ ] Check the release notes for **behaviour changes** in the APIs we use
      (FastAPI middleware order, asyncpg cursor behaviour, httpx timeouts,
      Playwright browser protocol changes, Postgres major-version changes).
- [ ] Scan for **security advisories** affecting the pinned version.
- [ ] Confirm the pin is compatible with the **Python 3.12** target
      (`python3.12 -m venv … && pip install -r …`).

## Upgrade procedure

1. **Backup first** — `bash infra/backup.sh 14` (and confirm the dump exists).
2. **Branch** — one upgrade per branch, one upstream per branch.
3. **Bump the pin** — `requirements.txt` (exact version), image tag, or
   `playwright==` line. No ranges, no `latest`.
4. **Local verification** — `pnpm verify` (lint → compile → unit + integration
   tests on real Postgres → typecheck → dashboard build → compose/CI/extension
   checks → browser E2E). It must be green before anything else happens.
5. **Container check** — `docker compose -f infra/docker/docker-compose.yml up -d --profile workers --profile storage`
   and watch the worker logs for one full cycle (collector → batch → render → publish → metrics → monitor).
6. **Restore drill** — `bash infra/restore.sh <newest dump>` into a throwaway DB.
7. **Merge + deploy** — tag the release, deploy, then watch the same cycles.
8. **Record** — update `docs/third-party-notices.md` (version + any license
   change) and note the outcome here.

## Major-version upgrades (Postgres, Python, Playwright browser)

- Do them in staging first, with a restored copy of production data.
- Postgres major: `backup → restore-drill → upgrade → verify row counts →
  re-run the test suite against the NEW major`.
- Never upgrade Postgres and the application in the same step.

## Rollback

- Application code: revert the merge (pinned versions are in git).
- Database schema: migrations are forward-only; a down-migration is a
  reviewed, hand-written file — never an automatic reverse of a data change.
- Images: redeploy the previous pinned tag (that is why we pin exact tags).

## Cadence

- **Monthly**: `.github/workflows/dependency-watch.yml` reports newer versions
  of the pinned Python packages and images (read-only — it never edits pins).
- **Quarterly**: re-read the licenses of every adopted upstream
  (`docs/third-party-notices.md`) and prune what we no longer use.
- **On advisory**: patch immediately, using this checklist with the backup
  step and the test suite as the gate.
