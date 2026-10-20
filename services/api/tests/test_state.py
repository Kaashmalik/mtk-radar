"""State machine tests - the hard rule: unverified offers cannot advance."""

import pytest

from state import (
    OFFER_STATES,
    VIDEO_ALLOWED_STATES,
    can_generate_video,
    can_transition,
    requires_review,
)


class TestHappyPath:
    def test_full_lifecycle(self):
        path = [
            ("candidate", "evidence_needed"),
            ("evidence_needed", "verified"),
            ("verified", "approved_for_video"),
            ("approved_for_video", "published"),
            ("published", "expired"),
            ("expired", "evidence_needed"),  # recoverable after expiry
        ]
        for frm, to in path:
            assert can_transition(frm, to), f"{frm} -> {to} must be allowed"

    def test_correction_path(self):
        assert can_transition("verified", "evidence_needed")
        assert can_transition("expired", "evidence_needed")

    def test_all_states(self):
        assert set(OFFER_STATES) == {
            "candidate", "evidence_needed", "verified", "approved_for_video",
            "published", "expired", "corrected",
        }


class TestBlockedTransitions:
    @pytest.mark.parametrize("target", ["verified", "approved_for_video", "published"])
    def test_candidate_blocked(self, target):
        assert not can_transition("candidate", target)

    @pytest.mark.parametrize("target", ["verified", "approved_for_video", "published"])
    def test_evidence_needed_only_advances_to_verified(self, target):
        assert can_transition("evidence_needed", target) == (target == "verified")

    def test_no_shortcuts_to_published(self):
        assert not can_transition("candidate", "published")
        assert not can_transition("evidence_needed", "published")
        assert not can_transition("verified", "published")  # must be approved first

    def test_published_cannot_go_backwards(self):
        assert not can_transition("published", "approved_for_video")
        assert not can_transition("published", "candidate")


class TestVideoGate:
    @pytest.mark.parametrize("state", ["candidate", "evidence_needed"])
    def test_video_blocked_before_verified(self, state):
        assert not can_generate_video(state)

    @pytest.mark.parametrize("state", ["verified", "approved_for_video", "published"])
    def test_video_allowed_after_verified(self, state):
        assert can_generate_video(state)

    def test_video_allowed_states_are_valid(self):
        assert VIDEO_ALLOWED_STATES <= set(OFFER_STATES)


class TestReviewGate:
    def test_approval_targets_need_reviewer(self):
        assert requires_review("approved_for_video")
        assert requires_review("published")

    def test_machine_transitions_do_not(self):
        assert not requires_review("verified")
        assert not requires_review("evidence_needed")
