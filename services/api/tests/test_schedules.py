"""Schedule queue state machine + platform metadata tests (§17)."""

import pytest

from schedules_state import (
    PLATFORM_LIMITS,
    PLATFORMS,
    TRANSITIONS,
    can_transition,
    default_publish_window,
    platform_metadata,
    script_version_hash,
    validate_transition,
)


class TestQueueStates:
    def test_plan_queue_states_exist(self):
        assert set(TRANSITIONS) == {
            "draft", "needs_approval", "approved", "scheduled",
            "published", "failed", "paused",
        }

    def test_happy_path(self):
        path = [
            ("draft", "needs_approval"),
            ("needs_approval", "approved"),
            ("approved", "scheduled"),
            ("scheduled", "published"),
        ]
        for frm, to in path:
            assert can_transition(frm, to), f"{frm} -> {to}"

    def test_pause_always_available_before_publish(self):
        for state in ("approved", "scheduled"):
            assert can_transition(state, "paused")
        assert can_transition("paused", "scheduled")  # resume, revalidated upstream
        assert can_transition("failed", "scheduled")  # retry eligible failures
        assert not can_transition("published", "scheduled")  # terminal

    def test_no_shortcuts(self):
        assert not can_transition("draft", "scheduled")
        assert not can_transition("draft", "approved")
        assert not can_transition("scheduled", "approved")


class TestValidateTransition:
    def test_approval_requires_reviewer_and_hash(self):
        with pytest.raises(Exception, match="reviewer"):
            validate_transition("needs_approval", "approved", reviewer=None, version_hash=None)
        with pytest.raises(Exception, match="version hash"):
            validate_transition("needs_approval", "approved", reviewer="kashif", version_hash=None)
        assert validate_transition("needs_approval", "approved",
                                   reviewer="kashif", version_hash="abc") == "abc"

    def test_scheduling_requires_hash(self):
        with pytest.raises(Exception, match="version hash"):
            validate_transition("approved", "scheduled", reviewer=None, version_hash=None)
        assert validate_transition("approved", "scheduled", reviewer=None,
                                   version_hash="abc") == "abc"

    def test_illegal_raises(self):
        with pytest.raises(Exception, match="illegal"):
            validate_transition("draft", "approved", reviewer="k", version_hash="h")

    def test_pause_needs_no_reviewer(self):
        assert validate_transition("scheduled", "paused", reviewer=None, version_hash=None) == ""


class TestVersionHash:
    def test_binds_to_exact_content(self):
        h1 = script_version_hash("# v1\ncontent")
        h2 = script_version_hash("# v2\ncontent")
        assert h1 != h2
        assert script_version_hash("# v1\ncontent") == h1  # deterministic


OEFFER = {
    "id": "o1",
    "title": "One-year .tech domain promotion",
    "provider": ".TECH Domains",
    "eligibility": {"countries": ["PK", "US"], "studentStatus": True},
    "renewal": {"autoRenew": True, "regularPrice": "$49.99/yr"},
}


class TestPlatformMetadata:
    def test_all_platforms_supported(self):
        assert set(PLATFORMS) == {"youtube", "facebook", "instagram", "tiktok"}

    def test_youtube_gets_title_and_caption(self):
        meta = platform_metadata("youtube", OEFFER,
                                 ["https://get.tech/terms"], {"synthetic_narration": False})
        assert len(meta["title"]) <= PLATFORM_LIMITS["youtube"]["title"]
        assert "renew" in meta["caption"].lower() or "$49.99" in meta["caption"]
        assert "https://get.tech/terms" in meta["caption"]
        assert meta["privacy_default"] == "private"

    def test_tiktok_caption_limit_enforced(self):
        for _ in range(20):
            OEFFER["eligibility"].setdefault("countries", []).append("EX")
        meta = platform_metadata("tiktok", OEFFER, [], {})
        assert len(meta["caption"]) <= PLATFORM_LIMITS["tiktok"]["caption"]
        assert not meta["title"]  # tiktok has no title

    def test_synthetic_narration_disclosed(self):
        meta = platform_metadata("youtube", OEFFER, [],
                                 {"synthetic_narration": True})
        assert "AI-generated" in meta["caption"]

    def test_unknown_platform_raises(self):
        with pytest.raises(ValueError):
            platform_metadata("twitter", OEFFER, [], {})


class TestPlatformMetadataUnknownWording:
    """Metadata must not turn an unchecked fact into a promise (A13)."""

    BARE = {"id": "o2", "title": "Free trial", "provider": "Acme",
            "eligibility": {}, "renewal": {}}

    def test_no_genuine_end_to_end_claim(self):
        caption = platform_metadata("youtube", self.BARE, [], {})["caption"]
        assert "Genuine end-to-end claim" not in caption
        assert "Results depend on your account and eligibility" in caption

    def test_unknown_eligibility_states_the_unknown(self):
        caption = platform_metadata("youtube", self.BARE, [], {})["caption"]
        assert "Eligibility not stated in the inspected terms" in caption
        assert "Open to everyone" not in caption

    def test_unknown_renewal_is_not_free(self):
        caption = platform_metadata("youtube", self.BARE, [], {})["caption"]
        assert "unknown renewal is not free" in caption.lower()
        assert "no ongoing cost" not in caption.lower()


class TestPublishWindow:
    def test_next_18_pk_slot(self):
        assert "T13:00" in default_publish_window()  # 13:00 UTC == 18:00 PKT
