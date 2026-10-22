"""Language policy: English-first packaging with opt-in Urdu voiceover."""

import pytest

from settings_api import normalize_setting


class TestLanguagePolicy:
    def test_defaults_are_english_first(self):
        policy = normalize_setting("language_policy", {})
        assert policy["metadata_language"] == "en"
        assert policy["captions_language"] == "en"
        assert policy["narration_languages"] == ["en"]
        assert policy["default_narration_language"] == "en"
        assert policy["urdu_voiceover_enabled"] is False

    def test_urdu_is_opt_in_for_narration_only(self):
        policy = normalize_setting("language_policy", {
            "metadata_language": "en",
            "captions_language": "en",
            "narration_languages": ["en", "ur"],
            "default_narration_language": "ur",
        })
        assert policy["narration_languages"] == ["en", "ur"]
        assert policy["default_narration_language"] == "ur"
        assert policy["urdu_voiceover_enabled"] is True
        # Packaging stays English even when the voiceover is Urdu.
        assert policy["metadata_language"] == "en"
        assert policy["captions_language"] == "en"

    def test_languages_are_deduplicated(self):
        policy = normalize_setting("language_policy", {
            "narration_languages": ["ur", "en", "ur"],
        })
        assert policy["narration_languages"] == ["ur", "en"]
        assert policy["default_narration_language"] == "ur"

    def test_unknown_language_rejected(self):
        with pytest.raises(ValueError, match="unsupported narration language"):
            normalize_setting("language_policy", {"narration_languages": ["en", "fr"]})

    def test_unknown_copy_language_rejected(self):
        with pytest.raises(ValueError, match="metadata_language"):
            normalize_setting("language_policy", {"metadata_language": "fr"})

    def test_default_narration_must_be_enabled(self):
        with pytest.raises(ValueError, match="default_narration_language"):
            normalize_setting("language_policy", {
                "narration_languages": ["en"],
                "default_narration_language": "ur",
            })
