"""Usage cost estimates (M7) — pure function, no database."""

from costs_store import estimate_cost


def test_paid_tts_is_priced_per_character():
    assert estimate_cost("tts", 1_000_000) > 0


def test_verified_local_tts_is_free_and_only_an_explicit_true_counts():
    assert estimate_cost("tts", 1_000_000, {"local": True}) == 0.0
    assert estimate_cost("tts", 1_000_000, {"local": "true"}) > 0, "strict boolean"
    assert estimate_cost("tts", 1_000_000, {"local": False}) > 0
