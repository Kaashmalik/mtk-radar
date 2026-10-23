"""Prometheus `/metrics` endpoint (v0.33).

Text exposition format, version 1 (industry standard, scrapeable by
Prometheus/VictoriaMetrics/Agent without converters). Protected by the same
bearer-token gate as every other route — configure the token in the scraper's
`authorization` — so metrics never leak offer or traffic data.

Design notes:
- cheap aggregates only: GROUP BY counts, no row materialization. A scrape
  every 15s must not compete with the workload.
- request counters come from the hardening middleware (route templates, so
  label cardinality stays bounded).
- the endpoint deliberately exposes NO per-entity data: state totals only.
"""

from fastapi import APIRouter, Response

import api_hardening
import db
import health_api

router = APIRouter(tags=["metrics"])

_PROM_FACT = "# TYPE %s %s"


def _render_prometheus(counters: dict[tuple[str, str, str], int],
                       jobs: dict, schedules: dict,
                       offers: dict, renders: int,
                       auth_failures: int, version: str) -> str:
    lines: list[str] = [
        _PROM_FACT % ("mtk_build_info", "gauge"),
        f'mtk_build_info{{version="{version}"}} 1',
        _PROM_FACT % ("mtk_api_requests_total", "counter"),
    ]
    for (method, path, status_class), count in sorted(counters.items()):
        lines.append(
            f'mtk_api_requests_total{{method="{method}",path="{path}",'
            f'status="{status_class}"}} {count}'
        )
    lines.append(_PROM_FACT % ("mtk_api_auth_failures_current", "gauge"))
    lines.append(f"mtk_api_auth_failures_current {auth_failures}")

    lines.append(_PROM_FACT % ("mtk_jobs", "gauge"))
    for status, kind, count in jobs:
        lines.append(f'mtk_jobs{{status="{status}",kind="{kind}"}} {count}')

    lines.append(_PROM_FACT % ("mtk_schedules", "gauge"))
    for state, count in schedules:
        lines.append(f'mtk_schedules{{state="{state}"}} {count}')

    lines.append(_PROM_FACT % ("mtk_offers", "gauge"))
    for state, count in offers:
        lines.append(f'mtk_offers{{state="{state}"}} {count}')

    lines.append(_PROM_FACT % ("mtk_renders_total", "gauge"))
    lines.append(f"mtk_renders_total {renders}")
    lines.append("")
    return "\n".join(lines)


@router.get("/metrics")
async def metrics(response: Response) -> Response:
    pool = db.get()

    jobs = await pool.fetch(
        "SELECT status::text AS status, kind, count(*)::int AS n "
        "FROM jobs GROUP BY status, kind ORDER BY status, kind"
    )
    schedules = await pool.fetch(
        "SELECT state::text AS state, count(*)::int AS n "
        "FROM schedules GROUP BY state ORDER BY state"
    )
    offers = await pool.fetch(
        "SELECT state::text AS state, count(*)::int AS n "
        "FROM offers GROUP BY state ORDER BY state"
    )
    renders = await pool.fetchval("SELECT count(*)::int FROM renders")

    counters = api_hardening.request_counter_snapshot()
    auth_failures = api_hardening.auth_failure_ips()

    body = _render_prometheus(
        counters, jobs, schedules, offers, renders or 0,
        auth_failures, health_api.APP_VERSION,
    )
    return Response(
        content=body,
        media_type="text/plain; version=1.0.0; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )
