"""WP-G robustness close-outs (enhancement plan 2026-10-24 §5.6): bulk un-wedge
(human-only, filter-checked), the render job lease heartbeat, and the media
GC retention job (90 days, pinned artifacts exempt, dry run first).
"""

import uuid as uuidlib
from pathlib import Path

import pytest

# Shared session fixture: wiped schema + migrated + the real app (with auth
# DISABLED — credential checks pass; auth_client covers the 401/403 rules).
from test_integration import _run, auth_client, client  # noqa: F401

from test_integration import AUTH, REVIEWER, SVC  # noqa: F401


# ------------------------------------------------------- /jobs/bulk-retry

def _dead_job(marker: str, *, status: str = "dead", kind: str = "collect") -> uuidlib.UUID:
    job_id = uuidlib.uuid4()
    _run(
        """
        INSERT INTO jobs (id, kind, entity_id, payload, dedupe_key, status,
                          run_after, attempts, max_attempts, last_error)
        VALUES ($1, $2, NULL, '{}'::jsonb, $3, $4, now() - interval '1 hour', 5, 5, 'outage')
        """,
        job_id, kind, f"bulk:{marker}:{job_id}", status,
    )
    return job_id


def test_bulk_retry_revives_only_dead_and_failed_jobs(client):
    marker = uuidlib.uuid4().hex
    dead = _dead_job(marker + "-dead", status="dead")
    failed = _dead_job(marker + "-failed", status="failed", kind="render_package")
    leased = _dead_job(marker + "-leased", status="leased")
    pending = _dead_job(marker + "-pending", status="pending")

    r = client.post("/jobs/bulk-retry", json={
        "ids": [str(dead), str(failed), str(leased), str(pending)]})
    assert r.status_code == 200, r.text
    body = r.json()
    by_id = {item["id"]: item for item in body["results"]}
    assert by_id[str(dead)]["ok"] is True
    assert by_id[str(failed)]["ok"] is True
    assert by_id[str(leased)]["ok"] is False, "leased work is in flight — never re-armed"
    assert by_id[str(pending)]["ok"] is False
    assert body["retried"] == 2

    states = {str(row["id"]): row["status"] for row in _run(
        "SELECT id, status::text AS status FROM jobs WHERE id = ANY($1::uuid[])",
        [str(j) for j in (dead, failed, leased, pending)])}
    assert states[str(dead)] == "pending" and states[str(failed)] == "pending"
    assert states[str(leased)] == "leased"
    assert states[str(pending)] == "pending"
    # fresh attempt budget + due now
    row = _run("SELECT attempts, last_error, run_after <= now() AS due "
               "FROM jobs WHERE id = $1", dead)[0]
    assert row["attempts"] == 0 and row["last_error"] is None and row["due"]


def test_bulk_retry_kinds_filter_and_unknown_kind_are_checked(client):
    marker = uuidlib.uuid4().hex
    dead_collect = _dead_job(marker + "-c", status="dead", kind="collect")
    dead_render = _dead_job(marker + "-r", status="dead", kind="render_package")

    r = client.post("/jobs/bulk-retry", json={"all": True, "kinds": ["collect"]})
    assert r.status_code == 200
    retried_ids = {item["id"] for item in r.json()["results"] if item["ok"]}
    assert str(dead_collect) in retried_ids
    assert str(dead_render) not in retried_ids, "the kind filter is respected"

    assert client.post(
        "/jobs/bulk-retry", json={"all": True, "kinds": ["not-a-kind"]}
    ).status_code == 422
    assert client.post("/jobs/bulk-retry", json={}).status_code == 422


def test_bulk_retry_is_a_human_action(auth_client):
    """Service credentials are refused outright — automation never bulk-requeues
    on its own (same rule as batch transitions)."""
    refused = auth_client.post("/jobs/bulk-retry", headers=SVC, json={"all": True})
    assert refused.status_code == 403, refused.text


def test_bulk_retry_writes_an_audit_entry(client):
    marker = uuidlib.uuid4().hex
    dead = _dead_job(marker, status="dead")
    r = client.post("/jobs/bulk-retry", json={"ids": [str(dead)]})
    assert r.status_code == 200
    audit = _run("SELECT detail FROM audit_log WHERE action = 'jobs:bulk_retry' "
                 "ORDER BY id DESC LIMIT 1")[0]["detail"]
    assert "retried" in audit


# --------------------------------------------------- /jobs/{id}/touch lease

def test_job_touch_extends_lease_for_the_current_holder_only(client):
    claim = client.post("/jobs/claim", json={
        "worker": "render-worker", "lease_s": 60, "kinds": ["collect"]})
    assert claim.status_code == 200, claim.text
    body = claim.json()
    if not body.get("claimed"):
        pytest.skip("no due collect job available to claim")
    job_id = body["id"]

    before = _run("SELECT lease_expires_at FROM jobs WHERE id = $1",
                  uuidlib.UUID(job_id))[0]
    touched = client.post(f"/jobs/{job_id}/touch",
                          json={"worker": "render-worker", "lease_s": 3600})
    assert touched.status_code == 200, touched.text
    after = _run("SELECT lease_expires_at FROM jobs WHERE id = $1",
                 uuidlib.UUID(job_id))[0]
    assert after["lease_expires_at"] > before["lease_expires_at"]

    hijack = client.post(f"/jobs/{job_id}/touch",
                         json={"worker": "someone-else", "lease_s": 3600})
    assert hijack.status_code == 409, "only the current holder may extend"


def test_job_result_is_fenced_to_the_current_holder(client):
    """A worker that lost its lease cannot overwrite the new holder's outcome;
    an unfenced (older) worker report is still accepted."""
    claim = client.post("/jobs/claim", json={
        "worker": "render-host-1", "lease_s": 60, "kinds": ["collect"]})
    assert claim.status_code == 200, claim.text
    body = claim.json()
    if not body.get("claimed"):
        pytest.skip("no due collect job available to claim")
    job_id = body["id"]

    stale = client.post(f"/jobs/{job_id}/result",
                        json={"ok": True, "worker": "render-host-2"})
    assert stale.status_code == 409, stale.text
    assert _run("SELECT status::text AS s FROM jobs WHERE id = $1",
                uuidlib.UUID(job_id))[0]["s"] == "leased", "nothing recorded"

    owner = client.post(f"/jobs/{job_id}/result",
                        json={"ok": True, "worker": "render-host-1"})
    assert owner.status_code == 200, owner.text
    assert owner.json()["status"] == "done"


# ---------------------------------------------------------------- media GC

def _rendered_offer(client, marker: str) -> str:
    """An old landscape render (120 days) whose offer is verified."""
    offer = client.post("/offers", json={
        "provider": f"GC {marker}", "category": "domains", "offer_type": "coupon",
    }).json()
    offer_id = uuidlib.UUID(offer["id"])
    _run("UPDATE offers SET state = 'verified' WHERE id = $1", offer_id)
    _run(
        "INSERT INTO evidence (offer_id, url, content_hash, official, domain_ok) "
        "VALUES ($1, 'https://official.example/gc', $2, TRUE, TRUE)",
        offer_id, f"gc-{marker}",
    )
    return offer["id"]


def _old_render(offer_id: str, marker: str) -> uuidlib.UUID:
    return _run(
        """
        INSERT INTO renders (offer_id, preset, width, height, video_path,
                             captions_path, created_at)
        VALUES ($1, 'landscape', 1920, 1080, $2, $3, now() - interval '120 days')
        RETURNING id
        """,
        uuidlib.UUID(offer_id),
        f"projects/gc/{marker}/video.mp4", f"projects/gc/{marker}/caps.vtt",
    )[0]["id"]


def test_media_gc_dry_run_candidates_exclude_pinned(client):
    marker = uuidlib.uuid4().hex
    # Old + UNPINNED: no schedule references this render.
    orphan_offer = _rendered_offer(client, marker + "-orphan")
    _old_render(orphan_offer, marker + "-orphan")
    # Old + PINNED: a live schedule references the render.
    pinned_offer = _rendered_offer(client, marker + "-pinned")
    pinned_render = _old_render(pinned_offer, marker + "-pinned")
    _run(
        """
        INSERT INTO projects (offer_id, state)
        VALUES ($1, 'approved')
        """,
        uuidlib.UUID(pinned_offer),
    )
    _run(
        """
        INSERT INTO schedules (offer_id, project_id, platform, local_time, render_id,
                               idempotency_key)
        SELECT p.offer_id, p.id, 'youtube', now() + interval '1 day', $2, $3
        FROM projects p WHERE p.offer_id = $1
        """,
        uuidlib.UUID(pinned_offer), pinned_render, f"gc-pin-{marker}",
    )
    pinned_count = _run("SELECT COUNT(*)::int AS n FROM schedules WHERE render_id = $1",
                        pinned_render)[0]["n"]
    assert pinned_count == 1, "test setup: the pinned schedule must exist"

    r = client.post("/media/gc", json={"dry_run": True, "retention_days": 90})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "dry_run"
    refs = {item["ref"] for item in body["items"]}
    assert f"projects/gc/{marker}-orphan/video.mp4" in refs
    assert f"projects/gc/{marker}-orphan/caps.vtt" in refs
    pinned_refs = [ref for ref in refs if marker + "-pinned" in ref]
    assert pinned_refs == [], "pinned renders (live schedule) are ALWAYS exempt"
    assert client.post("/media/gc", json={"dry_run": True}).status_code == 200


def test_media_gc_apply_deletes_and_audits(client):
    marker = uuidlib.uuid4().hex
    orphan_offer = _rendered_offer(client, marker + "-apply")
    _old_render(orphan_offer, marker + "-apply")
    # Real files inside the repo checkout so the legacy-path rule holds.
    for rel in (f"projects/gc/{marker}-apply/video.mp4",
                f"projects/gc/{marker}-apply/caps.vtt"):
        path = Path.cwd() / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"media")
    _run("UPDATE renders SET video_path = $2, captions_path = $3 "
         "WHERE offer_id = $1",
         uuidlib.UUID(orphan_offer),
         f"projects/gc/{marker}-apply/video.mp4",
         f"projects/gc/{marker}-apply/caps.vtt")

    r = client.post("/media/gc", json={"dry_run": False, "retention_days": 90})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "apply"
    assert body["deleted"] >= 2
    assert not (Path.cwd() / f"projects/gc/{marker}-apply/video.mp4").exists()
    assert not (Path.cwd() / f"projects/gc/{marker}-apply/caps.vtt").exists()
    audit = _run(
        "SELECT detail FROM audit_log WHERE action = 'media:gc' "
        "ORDER BY id DESC LIMIT 1")[0]["detail"]
    assert marker + "-apply" in audit


# ------------------------------------- media GC G27: reference-aware sweep

def _schedule_for_render(offer_id: str, render_id, marker: str, state: str):
    """A schedule row in ANY given state referencing the render (pins it)."""
    return _run(
        """
        INSERT INTO projects (offer_id, state) VALUES ($1, 'approved')
        RETURNING id
        """,
        uuidlib.UUID(offer_id),
    ) and _run(
        """
        INSERT INTO schedules (offer_id, project_id, platform, local_time,
                               state, render_id, idempotency_key)
        SELECT p.offer_id, p.id, 'youtube', now() + interval '1 day',
               $3::schedule_state, $2, $4
        FROM projects p WHERE p.offer_id = $1
        RETURNING id
        """,
        uuidlib.UUID(offer_id), render_id, state, f"gc27-{marker}",
    )[0]["id"]


def test_media_gc_failed_paused_and_published_schedules_all_pin(client):
    """G27: a schedule that is failed or paused (held) still pins its exact
    render and capture artifacts — evidence for the retry decision and human
    review must survive the retention sweep; ONLY a cancelled schedule
    releases artifacts."""
    for state in ("failed", "paused", "published", "approved", "draft"):
        marker = f"{uuidlib.uuid4().hex[:8]}-{state}"
        offer = _rendered_offer(client, marker)
        render = _old_render(offer, marker)
        _schedule_for_render(offer, render, marker, state)
        refs = {i["ref"] for i in client.post(
            "/media/gc", json={"dry_run": True, "retention_days": 90}
        ).json()["items"]}
        live = [ref for ref in refs if marker in ref]
        assert live == [], (
            f"a {state} schedule must pin its render artifacts; leaked {live}")


def test_media_gc_cancelled_schedule_releases_its_own_cover_only(client):
    """G27: a cancelled schedule's own cover file becomes collectible, and its
    schedule row keeps the dangling path only as a dead record."""
    marker = uuidlib.uuid4().hex[:8]
    offer = _rendered_offer(client, marker)
    _run(
        """
        INSERT INTO projects (offer_id, state) VALUES ($1, 'approved')
        """,
        uuidlib.UUID(offer),
    )
    rel = f"projects/gc/{marker}/cover.jpg"
    _run(
        """
        INSERT INTO schedules (offer_id, project_id, platform, local_time,
                               state, cover_path, created_at, idempotency_key)
        SELECT p.offer_id, p.id, 'youtube', now() - interval '120 days',
               'cancelled', $2, now() - interval '120 days', $3
        FROM projects p WHERE p.offer_id = $1
        """,
        uuidlib.UUID(offer), rel, f"gc27-cov-{marker}",
    )
    refs = {i["ref"] for i in client.post(
        "/media/gc", json={"dry_run": True, "retention_days": 90}).json()["items"]}
    assert rel in refs, "a cancelled schedule's own cover is collectible"


def test_media_gc_shared_file_reference_is_pinned_by_value_not_row(client):
    """G27: pinning is by artifact REF STRING as well as by row id. Two
    renders can point at the SAME cover file (shared export); GC of the
    unpinned render must not delete a file a live schedule still needs."""
    marker = uuidlib.uuid4().hex[:8]
    shared = f"projects/gc/{marker}/shared-cover.jpg"
    # offer A: pinned schedule → its render (and its cover) are pinned.
    offer_a = _rendered_offer(client, marker + "-a")
    render_a = _old_render(offer_a, marker + "-a")
    _run("UPDATE renders SET cover_path = $2 WHERE id = $1",
         render_a, shared)
    _schedule_for_render(offer_a, render_a, marker + "-a", "scheduled")
    # offer B: UNPINNED old render whose cover is THE SAME FILE.
    offer_b = _rendered_offer(client, marker + "-b")
    _run(
        """
        INSERT INTO renders (offer_id, preset, width, height, video_path,
                             captions_path, cover_path, created_at)
        VALUES ($1, 'landscape', 1920, 1080, $2, $3, $4,
                now() - interval '120 days')
        """,
        uuidlib.UUID(offer_b),
        f"projects/gc/{marker}-b/video.mp4",
        f"projects/gc/{marker}-b/caps.vtt",
        shared,
    )
    items = client.post("/media/gc",
                        json={"dry_run": True, "retention_days": 90}).json()["items"]
    by_ref = {i["ref"]: i["artifact"] for i in items}
    assert shared not in by_ref, (
        "a file shared with a pinned render must never be a GC candidate")
    assert f"projects/gc/{marker}-b/video.mp4" in by_ref
    assert f"projects/gc/{marker}-b/caps.vtt" in by_ref


def test_media_gc_apply_rechecks_pins_inside_the_sweep_lock(client, tmp_path):
    """G27: the GRACE between mark and sweep is honored by a SECOND pin check
    inside the advisory-locked apply transaction — anything pinned after the
    dry run (here: between mark and sweep) silently drops out, and the
    schedule INSERT itself serializes on the same lock."""
    marker = uuidlib.uuid4().hex[:8]
    orphan_offer = _rendered_offer(client, marker)
    _old_render(orphan_offer, marker)
    # real file so a delete would be observable
    rel = f"projects/gc/{marker}/video.mp4"
    path = Path.cwd() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"media-gc-g27")
    try:
        marked = client.post("/media/gc",
                             json={"dry_run": True, "retention_days": 90}).json()
        assert any(marker in i["ref"] for i in marked["items"]), \
            "setup: the artifact is a candidate while unpinned"

        # the pin arrives AFTER the dry-run mark, as a concurrent commit would
        render_id = _run("SELECT id FROM renders WHERE video_path = $1",
                         rel)[0]["id"]
        _schedule_for_render(orphan_offer, render_id, marker, "scheduled")

        applied = client.post("/media/gc",
                              json={"dry_run": False, "retention_days": 90}).json()
        assert applied["mode"] == "apply"
        assert not any(marker in r for r in applied.get("removed_refs", [])), \
            "the second pin check must drop a newly pinned artifact"
        assert path.exists(), "the pinned artifact must survive the sweep"
        # and the schedule that pins it was created through the same lock
        # path (INSERT under MEDIA_GC_LOCK_KEY) — proven by this thread making
        # both calls without deadlock.
    finally:
        import shutil
        shutil.rmtree(Path.cwd() / f"projects/gc/{marker}", ignore_errors=True)


# --------------------------------------------- trends summary is global (P2)

def test_trends_summary_is_global_while_page_total_names_the_page(client):
    """P2 carry-over (system-review 2026-10-23): the summary used to be
    page-local while reading as totals. The summary is now GLOBAL and
    `page_total` says exactly how many rows THIS page holds."""
    marker = uuidlib.uuid4().hex
    _run(
        """
        INSERT INTO trend_candidates (title, url, score, status)
        VALUES ('t1', $1, 90, 'shortlisted'), ('t2', $2, 82, 'radar'),
               ('t3', $3, 30, 'radar')
        """,
        f"https://trend.example/{marker}/a",
        f"https://trend.example/{marker}/b",
        f"https://trend.example/{marker}/c",
    )
    listed = client.get("/trends", params={"limit": 2})
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["page_total"] == len(body["candidates"]) == 2
    summary = body["summary"]
    assert summary["total"] > body["page_total"], (
        "summary counts the whole radar, not the page")
    hot = int(_run("SELECT COUNT(*)::int AS n FROM trend_candidates "
                   "WHERE score >= 78")[0]["n"])
    shortlisted = int(_run("SELECT COUNT(*)::int AS n FROM trend_candidates "
                           "WHERE status = 'shortlisted'")[0]["n"])
    assert summary["hot"] == hot
    assert summary["shortlisted"] == shortlisted


# ------------------------------------- WP-H: conflict annotation + best-times

def _sched_setup(client, marker: str) -> list[str]:
    """One offer + project + n schedules (needs_approval) at controlled times."""
    offer = client.post("/offers", json={
        "provider": f"Cal {marker}", "category": "domains", "offer_type": "coupon",
    }).json()
    offer_id = uuidlib.UUID(offer["id"])
    _run("UPDATE offers SET state = 'verified' WHERE id = $1", offer_id)
    project = _run(
        "INSERT INTO projects (offer_id, state) VALUES ($1, 'approved') "
        "RETURNING id", offer_id)[0]
    return [offer["id"], str(project["id"])]


def _add_schedule(marker: str, offer_id: str, project_id: str, *,
                  platform: str, offset_min: int, state: str = "needs_approval",
                  tz: str = "Asia/Karachi") -> str:
    return str(_run(
        """
        INSERT INTO schedules (offer_id, project_id, platform, state, local_time,
                               timezone, idempotency_key)
        VALUES ($1, $2, $3, $4::schedule_state,
                now() + make_interval(mins => $5), $6, $7)
        RETURNING id
        """,
        uuidlib.UUID(offer_id), uuidlib.UUID(project_id), platform, state,
        offset_min, tz, f"cal-{marker}-{offset_min}-{platform}",
    )[0]["id"])


def test_same_platform_within_an_hour_is_flagged_as_conflict(client):
    marker = uuidlib.uuid4().hex[:8]
    offer_id, project_id = _sched_setup(client, marker)
    a = _add_schedule(marker, offer_id, project_id, platform="youtube", offset_min=+240)
    b = _add_schedule(marker, offer_id, project_id, platform="youtube", offset_min=+270)
    # same time, DIFFERENT platform → not a double-post
    c = _add_schedule(marker, offer_id, project_id, platform="facebook", offset_min=+250)
    # same platform, 5 h away → fine
    d = _add_schedule(marker, offer_id, project_id, platform="youtube", offset_min=+560)

    rows = {r["id"]: r for r in client.get("/schedules", params={"limit": 200}).json()}
    assert rows[a]["conflict"] is True and rows[b]["conflict"] is True
    assert set(rows[a]["conflict_with"]) == {b}
    assert set(rows[b]["conflict_with"]) == {a}
    assert rows[c]["conflict"] is False and rows[c]["conflict_with"] == []
    assert rows[d]["conflict"] is False


def test_conflicts_are_advisory_past_and_cancelled_posts_are_ignored(client):
    marker = uuidlib.uuid4().hex[:8]
    offer_id, project_id = _sched_setup(client, marker)
    # two posts 30 min apart but one is draft (never queued) and one cancelled:
    # no decision for the operator to make → no flag.
    e = _add_schedule(marker, offer_id, project_id, platform="tiktok",
                      offset_min=+120, state="draft")
    f = _add_schedule(marker, offer_id, project_id, platform="tiktok",
                      offset_min=+150, state="cancelled")
    rows = {r["id"]: r for r in client.get("/schedules", params={"limit": 200}).json()}
    assert rows[e]["conflict"] is False and rows[f]["conflict"] is False


def test_best_times_suggests_only_measured_hours(client):
    marker = uuidlib.uuid4().hex[:8]
    offer_id, project_id = _sched_setup(client, marker)
    # Platform A: two published post in the SAME measured local hour → suggested.
    # Platform B: published posts, NO metrics → must never be suggested.
    # Anchor both measured posts to the SAME local hour in Karachi, one local
    # day ago (date_trunc in the schedule's own tz → no host-timezone drift).
    anchor = """
        (date_trunc('hour', now() AT TIME ZONE 'Asia/Karachi')
         AT TIME ZONE 'Asia/Karachi') - interval '24 hours' + %s
    """
    def measured_post(suffix, offset):
        return str(_run(
            """
            INSERT INTO schedules (offer_id, project_id, platform, state,
                                   local_time, timezone, idempotency_key)
            VALUES ($1, $2, 'youtube', 'published', """ + anchor % offset + """,
                    'Asia/Karachi', $3)
            RETURNING id
            """,
            uuidlib.UUID(offer_id), uuidlib.UUID(project_id), f"cal-{marker}-{suffix}",
        )[0]["id"])
    a1 = measured_post("a1", "interval '5 minutes'")
    a2 = measured_post("a2", "interval '35 minutes'")
    b1 = _add_schedule(marker + "-bx", offer_id, project_id, platform="facebook",
                       offset_min=-720, state="published")
    b2 = _add_schedule(marker + "-by", offer_id, project_id, platform="facebook",
                       offset_min=-600, state="published")
    for sid, views in ((a1, 500), (a2, 300)):
        _run(
            "INSERT INTO post_metrics (schedule_id, platform, views, likes, "
            "comments, source) VALUES ($1, 'youtube', $2, 10, 5, 'test')",
            uuidlib.UUID(sid), views,
        )
    r = client.get("/schedules/best-times")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["min_sample_posts"] == 2
    assert body["engagement_blend_enabled"] is False, (
        "the derived blend is OFF by default (G21 permission switch)")
    assert "editorial heuristic" in body["ranking_method"]
    assert "views" in body["ranking_method"]
    suggestions = body["suggestions"]
    youtube = suggestions.get("youtube") or []
    assert any(h["local_hour"] is not None and h["sample_posts"] == 2
               for h in youtube), "two measured posts in one hour → suggested"
    assert "facebook" not in suggestions, (
        "unmeasured platforms suggest nothing — no invention")
    best = youtube[0]
    # default mode: native avg views, NO derived composite
    assert set(best) == {"local_hour", "sample_posts", "avg_views"}
    assert best["avg_views"] == 400  # mean of (500, 300)


def test_best_times_derived_blend_is_permission_gated(client, monkeypatch):
    """G21 (evidence-to-video plan): the views + 2×(likes+comments) blend is
    the same restricted derived-metric class as the growth score. Default OFF
    ranks by native avg views; the blend exists only under the explicit
    opt-in, is applied consistently, and is labeled as an internal signal."""
    marker = uuidlib.uuid4().hex[:8]
    offer_id, project_id = _sched_setup(client, marker)
    anchor = """
        (date_trunc('hour', now() AT TIME ZONE 'Asia/Karachi')
         AT TIME ZONE 'Asia/Karachi') - interval '24 hours' + %s
    """

    def measured_post(suffix, offset):
        return str(_run(
            """
            INSERT INTO schedules (offer_id, project_id, platform, state,
                                   local_time, timezone, idempotency_key)
            VALUES ($1, $2, 'youtube', 'published', """ + anchor % offset + """,
                    'Asia/Karachi', $3)
            RETURNING id
            """,
            uuidlib.UUID(offer_id), uuidlib.UUID(project_id), f"cal-{marker}-{suffix}",
        )[0]["id"])

    # Best-times buckets collapse to HOUR-OF-DAY (all days), so the offsets
    # below pick hours no other test in this file measures: H1 (+65/+75 min)
    # and H2 (+185/+195 min) — two distinct local hours, exclusively this
    # test's data despite the shared session DB.
    # hour H1: low views but heavy likes → high BLEND
    h1a = measured_post("h1a", "interval '65 minutes'")
    h1b = measured_post("h1b", "interval '75 minutes'")
    # hour H2 (two hours later): high views, no engagement
    h2a = measured_post("h2a", "interval '185 minutes'")
    h2b = measured_post("h2b", "interval '195 minutes'")
    for sid, views, likes, comments in (
            (h1a, 100, 100, 0), (h1b, 100, 100, 0),
            (h2a, 200, 0, 0), (h2b, 200, 0, 0)):
        _run(
            "INSERT INTO post_metrics (schedule_id, platform, views, likes, "
            "comments, source) VALUES ($1, 'youtube', $2, $3, $4, 'test')",
            uuidlib.UUID(sid), views, likes, comments,
        )

    monkeypatch.delenv("MTK_ENABLE_DERIVED_ENGAGEMENT", raising=False)

    # default: ranking by avg views puts H2 (200) ahead of H1 (100); the
    # blend is nowhere in the payload. (Earlier tests in this session may add
    # other measured youtube hours — filter to THIS test's two hours.)
    body = client.get("/schedules/best-times").json()
    assert body["engagement_blend_enabled"] is False
    mine = [h for h in body["suggestions"]["youtube"]
            if h["avg_views"] in (100.0, 200.0)]
    assert [h["avg_views"] for h in mine] == [200.0, 100.0], \
        "higher measured views lead under the default editorial ranking"
    assert all("avg_engagement" not in h for h in body["suggestions"]["youtube"])

    # explicit opt-in: the composite ranks H1 (100 + 2×100 = 300) above
    # H2 (200), and the response is labeled as an internal directional
    # signal — never as a platform metric.
    monkeypatch.setenv("MTK_ENABLE_DERIVED_ENGAGEMENT", "1")
    body = client.get("/schedules/best-times").json()
    assert body["engagement_blend_enabled"] is True
    assert "not a platform metric" in body["ranking_method"]
    blend = body["suggestions"]["youtube"]
    mine = [h for h in blend if h["avg_views"] in (100.0, 200.0)]
    assert [h["avg_engagement"] for h in mine] == [300.0, 200.0], \
        "with permission granted, the derived blend ranks H1 above H2"
    assert mine[0]["avg_views"] == 100.0 and mine[1]["avg_views"] == 200.0



def test_cost_per_video_counts_unique_packages_not_cross_posts(client):
    """M7: one video posted to two platforms is ONE video and TWO posts."""
    before = client.get("/costs/summary").json()
    marker = uuidlib.uuid4().hex[:8]
    offer_id, project_id = _sched_setup(client, marker)
    _add_schedule(marker, offer_id, project_id, platform="youtube",
                  offset_min=-30, state="published")
    _add_schedule(marker, offer_id, project_id, platform="facebook",
                  offset_min=-20, state="published")
    after = client.get("/costs/summary").json()
    assert after["published_posts_30d"] - before["published_posts_30d"] == 2
    assert after["published_videos_30d"] - before["published_videos_30d"] == 1
    if after["usd_30d"] > 0:
        assert after["cost_per_published_video_usd_30d"] >= \
            after["cost_per_published_post_usd_30d"]


def test_youtube_quota_ledger_reserves_atomically_and_refuses_past_the_limit(client, monkeypatch):
    """Q1: reservations count against the Pacific quota day; a request that
    would exceed the limit is refused with the reset time; released units
    return, consumed units stay spent."""
    monkeypatch.setenv("YOUTUBE_QUOTA_UNITS_PER_DAY", "5000")
    account = f"acct-{uuidlib.uuid4().hex[:8]}"

    def reserve(units):
        return client.post("/quota/reserve", json={
            "provider": "youtube", "account": account,
            "buckets": {"units": units}, "operation": "upload_package"})

    first = reserve(3000)
    assert first.status_code == 200 and first.json()["allowed"] is True, first.text
    refused = reserve(2500).json()
    assert refused["allowed"] is False and refused["reservation_id"] is None
    assert refused["buckets"]["units"]["remaining"] == 2000
    assert refused["retry_after_s"] > 0 and refused["resets_at"]

    rid = first.json()["reservation_id"]
    released = client.post(f"/quota/{rid}/settle", json={"status": "released"})
    assert released.status_code == 200 and released.json()["settled"] == 1
    assert reserve(4500).json()["allowed"] is True, "released units return to the pool"

    again = client.post(f"/quota/{rid}/settle", json={"status": "consumed"})
    assert again.json()["settled"] == 0, "a settled reservation never flips"
    assert client.post(f"/quota/{uuidlib.uuid4()}/settle",
                       json={"status": "consumed"}).status_code == 404
    unknown = client.post("/quota/reserve", json={
        "provider": "youtube", "account": account, "buckets": {"bogus": 1}})
    assert unknown.status_code == 422

    usage = client.get("/quota", params={"provider": "youtube"}).json()
    mine = [a for a in usage["accounts"] if a["account"] == account]
    assert mine and mine[0]["reserved"] == 4500
