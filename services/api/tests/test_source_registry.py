"""G06 (EP-02): the adapter registry is one authoritative list.

Before, `schemas.AdapterKind` allowed only five old kinds while five
implemented trend adapters were creatable only by bypassing the API with
seed SQL. These guards keep every layer in lockstep: if a new adapter is
registered but a layer is not updated (or vice versa), the suite fails
instead of sources silently failing at poll time.
"""

import importlib.util
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

import schemas

from source_adapters.registry import ADAPTERS, ADAPTER_KINDS, AdapterSpec
from source_adapters.registry import APPROVAL_PENDING

_REPO = Path(__file__).resolve().parents[3]


def _load_collector():
    sys.path.insert(0, str(_REPO / "workers" / "collectors"))
    try:
        spec = importlib.util.spec_from_file_location(
            "mtk_collector_main_registry_test",
            _REPO / "workers" / "collectors" / "main.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


# The five kinds that used to be the whole schema — plus everything added.
def test_api_adapter_literal_matches_registry():
    assert sorted(schemas.AdapterKind.__args__) == sorted(ADAPTER_KINDS), (
        "schemas.AdapterKind and source_adapters.registry drifted apart")


def test_registry_kinds_are_unique_and_described():
    assert len(ADAPTER_KINDS) == len(set(ADAPTER_KINDS))
    for kind, spec in ADAPTERS.items():
        assert isinstance(spec, AdapterSpec)
        assert spec.label and spec.description


def test_every_registered_kind_is_creatable_via_the_api(monkeypatch):
    """The acceptance criterion: the API validates and can create each
    adapter kind. Approval-pending kinds (G22) are recordable DISABLED until
    their lift env is set."""
    monkeypatch.delenv("MTK_ENABLE_REDDIT_ADAPTER", raising=False)
    for kind, spec in ADAPTERS.items():
        config = {key: f"test-{key}" for key in spec.config_required}
        if kind == "github_stars":
            config["repos"] = ["owner/name"]
        source = schemas.SourceIn(
            provider="Registry Probe", category="test", adapter=kind,
            config=config, enabled=kind not in APPROVAL_PENDING)
        assert source.adapter == kind


def test_required_adapter_config_is_enforced_at_creation():
    """A kind with required config must fail registration without it — the
    collector used to be the first to discover the hole, at poll time."""
    for kind, spec in ADAPTERS.items():
        if not spec.config_required:
            continue
        with pytest.raises(ValidationError, match="requires config key"):
            schemas.SourceIn(
                provider="Registry Probe", category="test",
                adapter=kind, config={})


def test_seeded_sources_validate_against_the_api_schema():
    """The seed script validated nothing: SQL could insert adapter kinds the
    API refused, hiding drift. Every seed row must pass `SourceIn`."""
    spec = importlib.util.spec_from_file_location(
        "mtk_seed_sources_test", _REPO / "services" / "api" / "scripts" /
        "seed_sources.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(module.SOURCES) >= 10, "seed list unexpectedly shrank"
    for src in module.SOURCES:
        schemas.SourceIn(**src)


def test_collector_dispatches_every_polled_kind_and_rejects_unknown():
    """The collector used to answer unknown adapters with `[]` silently —
    a typo in seed SQL left the source green while polling nothing."""
    collector = _load_collector()

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {}

    class FakeFetcher:
        def fetch_policy(self, url, **kwargs):
            raise AssertionError(f"network fetch attempted: {url}")

    polled = {kind for kind, spec in ADAPTERS.items() if spec.collector_polled}
    not_polled = set(ADAPTER_KINDS) - polled
    assert polled and not_polled

    for kind in not_polled:
        assert collector.collect({"adapter": kind}, FakeFetcher()) == [], kind

    # Unknown kind == loud data bug, never an empty success.
    with pytest.raises(ValueError, match="unknown adapter kind"):
        collector.collect({"adapter": "typo_kinnd"}, FakeFetcher())

    # Every polled kind at least runs its dispatch path: missing required
    # config raises the adapter's own ValueError instead of returning [].
    # (Approval-pending kinds stop earlier, at the approval gate — covered by
    # the dedicated G22 tests below.)
    for kind in polled - set(APPROVAL_PENDING):
        spec = ADAPTERS[kind]
        if not spec.config_required:
            continue
        with pytest.raises(ValueError):
            collector.collect({"adapter": kind, "config": {}}, FakeFetcher())


# ------------------------------------------------- G22 [S10]: reddit is OFF

def test_reddit_is_approval_pending_and_off_by_default(monkeypatch):
    from source_adapters.registry import APPROVAL_PENDING, approval_denial

    monkeypatch.delenv("MTK_ENABLE_REDDIT_ADAPTER", raising=False)
    assert "reddit_new" in APPROVAL_PENDING, \
        "G22: reddit must be approval-pending in the registry"
    assert approval_denial("reddit_new") is not None
    assert approval_denial("rss") is None


def test_enabled_reddit_source_is_refused_disabled_is_recordable(monkeypatch):
    monkeypatch.delenv("MTK_ENABLE_REDDIT_ADAPTER", raising=False)
    with pytest.raises(ValidationError, match="disabled pending"):
        schemas.SourceIn(
            provider="Reddit r/X", category="trend_signals", adapter="reddit_new",
            config={"subreddit": "x"}, enabled=True)
    # Recording the intent ahead of approval stays allowed…
    disabled = schemas.SourceIn(
        provider="Reddit r/X", category="trend_signals", adapter="reddit_new",
        config={"subreddit": "x"}, enabled=False)
    assert disabled.enabled is False
    # …and an operator lift re-enables creation.
    monkeypatch.setenv("MTK_ENABLE_REDDIT_ADAPTER", "1")
    schemas.SourceIn(
        provider="Reddit r/X", category="trend_signals", adapter="reddit_new",
        config={"subreddit": "x"}, enabled=True)


def test_collector_refuses_approval_pending_adapters(monkeypatch):
    collector = _load_collector()
    monkeypatch.delenv("MTK_ENABLE_REDDIT_ADAPTER", raising=False)
    with pytest.raises(PermissionError, match="approval"):
        collector.collect(
            {"adapter": "reddit_new",
             "config": {"subreddit": "localllama"}},
            fetcher=None)
    monkeypatch.setenv("MTK_ENABLE_REDDIT_ADAPTER", "1")

    class NetRefuser:
        def fetch_policy(self, url, **kwargs):
            raise AssertionError(f"network fetch attempted: {url}")

    # Lifted: the approval gate passes and dispatch proceeds (the fake
    # fetcher refuses any actual network access — never an approval denial).
    with pytest.raises(AssertionError, match="network fetch"):
        collector.collect(
            {"adapter": "reddit_new", "config": {"subreddit": "localllama"}},
            fetcher=NetRefuser())


def test_seed_records_reddit_disabled_but_valid():
    """Seed rows pass SourceIn (G06) AND reddit ships disabled (G22): the
    approval, not a schema bypass, is the only missing step."""
    spec = importlib.util.spec_from_file_location(
        "mtk_seed_sources_test_g22", _REPO / "services" / "api" / "scripts" /
        "seed_sources.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reddit = [s for s in module.SOURCES if s["adapter"] == "reddit_new"]
    assert reddit, "seed list must still record the reddit intent"
    assert all(s.get("enabled") is False for s in reddit), \
        "G22: seeded reddit sources must ship disabled"
