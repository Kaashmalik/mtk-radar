# Third-Party Notices

Record every adopted upstream here — repo, pinned version, license, integration tier, and obligation notes. See `open-source-integrations.md` for the evaluation rationale.

| Project | Pinned version | License | Integration tier | Notes / obligations |
|---|---|---|---|---|
| FastAPI + uvicorn | requirements.txt pins | MIT/Apache-2.0 (BSD-style) | Library | Standard attribution |
| asyncpg | requirements.txt pins | Apache-2.0 | Library | — |
| Next.js / React | apps/dashboard/package.json | MIT | Library | Vercel templates compliance N/A |
| zod | packages/offer-schema | MIT | Library | — |
| PostgreSQL 16 | infra/docker | PostgreSQL License | Service (container) | Postgres License requires notice retention |
| Redis 7 | infra/docker | RSALv2/SSPLv1 binary; client MIT | Service (container) | Self-host binary use is fine; no redistribution of forks |
| dgtlmoon/changedetection.io | TBD at adoption | Check repo at pin | Integrate (container) | Collector use only; not validity proof |
| gitroomhq/postiz-app | TBD at adoption | AGPL-3.0 | Integrate (optional) | AGPL network-use obligations if modified/hosted for users |
| n8n-io/n8n | TBD at adoption | Sustainable Use License | Integrate (dev/prototype) | Not OSI open source; restrict internal use |
| microsoft/playwright | TBD at adoption | Apache-2.0 | Library | — |
| FFmpeg | TBD build config | LGPL/GPL per build | Vendor binary | Codec/patent config must be reviewed before distribution |
| Remotion | Not adopted yet | Source-available / commercial | Pending evaluation | Review pricing for business use before any template code |

## Rules

1. Pin exact versions; floating tags are not allowed in deployments.
2. Never commit upstream source into this repository.
3. Re-verify the LICENSE file at the pinned version at every adoption and upgrade.
4. Any fork we must maintain is documented here with its delta and upstream-PR link.
