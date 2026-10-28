"""Calendar conflict detection (G26) — pure-function tests, no database.

Conflicts compare absolute instants per platform ACCOUNT, so local-midnight
splits, display timezones and keyset page boundaries cannot hide a
double-post, while two different channels on one platform never collide.
"""

from datetime import datetime, timedelta, timezone

from schedules_api import _annotate_conflicts

T0 = datetime(2026, 10, 28, 18, 50, tzinfo=timezone.utc)


def _row(id_, minutes, platform="youtube", account="acc-1", state="scheduled",
         tz="Asia/Karachi"):
    return {"id": id_, "platform": platform, "platform_account_id": account,
            "state": state, "local_time": T0 + timedelta(minutes=minutes),
            "timezone": tz}


def test_same_account_within_window_conflicts_both_ways():
    rows = [_row("a", 0), _row("b", 30)]
    _annotate_conflicts(rows)
    assert rows[0]["conflict_with"] == ["b"] and rows[1]["conflict_with"] == ["a"]


def test_local_midnight_no_longer_splits_a_conflict():
    # 23:50 and 00:10 Karachi time (UTC+5): 20 minutes apart, different local days.
    late = _row("late", 0)
    early = _row("early", 20)
    late["local_time"] = datetime(2026, 10, 28, 18, 50, tzinfo=timezone.utc)
    early["local_time"] = datetime(2026, 10, 28, 19, 10, tzinfo=timezone.utc)
    rows = [late, early]
    _annotate_conflicts(rows)
    assert rows[0]["conflict"] and rows[1]["conflict"]


def test_different_display_timezones_compare_by_instant():
    rows = [_row("pk", 0, tz="Asia/Karachi"), _row("utc", 15, tz="UTC")]
    _annotate_conflicts(rows)
    assert rows[0]["conflict"] and rows[1]["conflict"]


def test_different_accounts_on_one_platform_do_not_conflict():
    rows = [_row("a", 0, account="channel-1"), _row("b", 5, account="channel-2")]
    _annotate_conflicts(rows)
    assert not rows[0]["conflict"] and not rows[1]["conflict"]


def test_unpinned_account_is_conservatively_a_possible_conflict():
    rows = [_row("a", 0, account=None), _row("b", 5, account="channel-2")]
    _annotate_conflicts(rows)
    assert rows[0]["conflict"] and rows[1]["conflict"]


def test_neighbour_on_another_page_is_detected_but_not_annotated():
    page = [_row("mine", 0)]
    other_page = [_row("next-page", 10)]
    _annotate_conflicts(page, context=other_page)
    assert page[0]["conflict_with"] == ["next-page"]
    assert "conflict" not in other_page[0], "context rows are read-only"


def test_window_edges_and_inactive_states():
    rows = [
        _row("a", 0),
        _row("edge", 60),               # exactly the window → conflict
        _row("far", 121),               # beyond the window of "edge"
        _row("draft", 1, state="draft"),        # not going out yet
        _row("done", 2, state="published"),     # post-mortem, not a decision
        _row("other-platform", 3, platform="facebook"),
    ]
    _annotate_conflicts(rows)
    by_id = {r["id"]: r for r in rows}
    assert by_id["a"]["conflict_with"] == ["edge"]
    assert set(by_id["edge"]["conflict_with"]) == {"a"}
    assert not by_id["far"]["conflict"]
    for quiet in ("draft", "done", "other-platform"):
        assert by_id[quiet]["conflict"] is False and by_id[quiet]["conflict_with"] == []
