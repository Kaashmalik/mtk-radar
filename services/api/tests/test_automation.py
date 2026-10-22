"""Automation policy validation + authorization (v0.26).

These are pure unit tests: no database, no HTTP. The policy is the contract
the API and every worker share, so its edges are tested here.
"""

import pytest

from automation import (
    AutomationDenied,
    PolicyError,
    authorize,
    can_automate,
    default_policy,
    describe,
    guardrails,
    is_automation_actor,
    list_presets,
    normalize_policy,
    preset_policy,
    stage_mode,
)


class TestDefaults:
    def test_default_is_assisted_not_autopilot(self):
        policy = default_policy()
        assert policy["mode"] == "assisted"
        assert policy["stages"]["approve"] == "human"
        assert policy["stages"]["schedule"] == "human"
        assert policy["stages"]["verify"] == "auto"
        assert policy["paused"] is False

    def test_every_stage_has_a_control(self):
        policy = default_policy()
        assert set(policy["stages"]) == {
            "collect", "verify", "script", "render", "approve", "schedule",
        }

    def test_presets_are_complete_and_safe(self):
        presets = list_presets()
        assert set(presets) == {"manual", "assisted", "autopilot"}
        assert set(presets["manual"]["stages"].values()) == {"human"}
        assert set(presets["autopilot"]["stages"].values()) == {"auto"}
        assert presets["manual"]["guardrails"]["auto_retry"] is False
        assert presets["autopilot"]["guardrails"]["auto_publish_max_per_day"] >= 0


class TestNormalize:
    def test_partial_update_keeps_unmentioned_stages(self):
        base = preset_policy("assisted")
        policy = normalize_policy({"stages": {"approve": "auto"}}, base=base)
        assert policy["stages"]["approve"] == "auto"
        assert policy["stages"]["verify"] == "auto"
        assert policy["mode"] == "custom"

    def test_partial_update_on_a_custom_policy_preserves_other_stages(self):
        base = normalize_policy({
            "mode": "assisted",
            "stages": {"render": "human", "schedule": "human"},
            "guardrails": {"auto_publish_max_per_day": 1},
        })
        assert base["mode"] == "custom"
        policy = normalize_policy({"stages": {"approve": "auto"}}, base=base)
        assert policy["stages"]["render"] == "human", \
            "editing one stage must not reset the rest to the assisted preset"
        assert policy["stages"]["approve"] == "auto"
        assert policy["guardrails"]["auto_publish_max_per_day"] == 1

    def test_pause_update_preserves_guardrails_and_stages(self):
        base = preset_policy("autopilot")
        base["guardrails"]["auto_publish_max_per_day"] = 1
        policy = normalize_policy({"paused": True}, base=base)
        assert policy["paused"] is True
        assert policy["guardrails"]["auto_publish_max_per_day"] == 1
        assert policy["stages"] == base["stages"]

    def test_mode_preset_replaces_stages_and_guardrail_defaults(self):
        base = preset_policy("autopilot")
        base["guardrails"]["auto_publish_max_per_day"] = 1
        policy = normalize_policy({"mode": "manual"}, base=base)
        assert set(policy["stages"].values()) == {"human"}
        assert policy["mode"] == "manual"
        assert policy["guardrails"]["auto_publish_max_per_day"] == 0  # manual preset

    def test_unknown_stage_is_rejected(self):
        with pytest.raises(PolicyError, match="unknown stage"):
            normalize_policy({"stages": {"teleport": "auto"}})

    def test_unknown_stage_mode_is_rejected(self):
        with pytest.raises(PolicyError, match="must be one of"):
            normalize_policy({"stages": {"verify": "sometimes"}})

    def test_unknown_guardrail_is_rejected(self):
        with pytest.raises(PolicyError, match="unknown guardrail"):
            normalize_policy({"guardrails": {"publish_everything": True}})

    def test_unknown_top_level_field_is_rejected(self):
        with pytest.raises(PolicyError, match="unknown policy field"):
            normalize_policy({"auto_publish": True})

    @pytest.mark.parametrize("value", [-1, 101, 2.5, "3"])
    def test_publish_budget_must_be_a_sane_integer(self, value):
        with pytest.raises(PolicyError):
            normalize_policy({"guardrails": {"auto_publish_max_per_day": value}})

    @pytest.mark.parametrize("value", [-0.1, 1.1, "high"])
    def test_confidence_must_be_a_fraction(self, value):
        with pytest.raises(PolicyError):
            normalize_policy({"guardrails": {"auto_verify_min_confidence": value}})

    def test_platforms_are_validated_and_deduplicated(self):
        policy = normalize_policy({"guardrails": {
            "auto_schedule_platforms": ["youtube", "youtube", "tiktok"]}})
        assert policy["guardrails"]["auto_schedule_platforms"] == ["youtube", "tiktok"]

    def test_empty_platform_list_is_rejected(self):
        with pytest.raises(PolicyError, match="non-empty"):
            normalize_policy({"guardrails": {"auto_schedule_platforms": []}})

    def test_unknown_platform_is_rejected(self):
        with pytest.raises(PolicyError, match="unknown platform"):
            normalize_policy({"guardrails": {"auto_schedule_platforms": ["myspace"]}})

    def test_privacy_is_validated(self):
        with pytest.raises(PolicyError, match="privacy"):
            normalize_policy({"guardrails": {"auto_schedule_privacy": "world"}})

    def test_paused_and_dry_run_are_booleans(self):
        with pytest.raises(PolicyError, match="true or false"):
            normalize_policy({"paused": "yes"})


class TestAuthorization:
    def test_auto_stage_allows_matching_automation_actor(self):
        policy = preset_policy("autopilot")
        assert can_automate(policy, "verify")
        assert authorize(policy, "verify", "automation:verify") == "automation:verify"

    def test_human_stage_denies_automation(self):
        policy = preset_policy("manual")
        assert not can_automate(policy, "verify")
        with pytest.raises(AutomationDenied, match="human control"):
            authorize(policy, "verify", "automation:verify")

    def test_paused_denies_everything(self):
        policy = preset_policy("autopilot")
        policy["paused"] = True
        with pytest.raises(AutomationDenied, match="paused"):
            authorize(policy, "schedule", "automation:schedule")

    def test_dry_run_denies_state_changes(self):
        policy = preset_policy("autopilot")
        policy["dry_run"] = True
        with pytest.raises(AutomationDenied, match="dry-run"):
            authorize(policy, "approve", "automation:approve")

    def test_actor_must_match_stage(self):
        policy = preset_policy("autopilot")
        with pytest.raises(AutomationDenied, match="cannot act on stage"):
            authorize(policy, "schedule", "automation:verify")

    def test_human_actor_is_always_refused_by_automation_path(self):
        with pytest.raises(AutomationDenied, match="named human reviewer"):
            authorize(preset_policy("autopilot"), "verify", "kashif")

    def test_actor_detection(self):
        assert is_automation_actor("automation:verify")
        assert is_automation_actor("AUTOMATION:schedule")
        assert not is_automation_actor("kashif")
        assert not is_automation_actor(None)


class TestDescribe:
    def test_summary_exposes_active_and_human_stages(self):
        summary = describe(preset_policy("assisted"))
        assert summary["state"] == "running"
        assert "verify" in summary["automation_stages"]
        assert "approve" in summary["human_stages"]
        assert summary["guardrails"]["auto_approve_requires_render"] is True
        assert summary["fixed_guarantees"]

    def test_paused_summary_reports_no_active_stage(self):
        policy = preset_policy("autopilot")
        policy["paused"] = True
        summary = describe(policy)
        assert summary["state"] == "paused"
        assert summary["automation_stages"] == []

    def test_guardrail_accessor_is_safe(self):
        assert guardrails()["auto_retry"] is True
        assert stage_mode(default_policy(), "approve") == "human"
