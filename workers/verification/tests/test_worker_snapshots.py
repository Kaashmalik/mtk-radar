"""One fetched text revision must be both persisted and extracted."""

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from allowlist import build_allowlist
from source_adapters.egress import EgressPolicy
from source_adapters.models import RawItem
from source_adapters.page_watch import fetch_page_snapshot
from source_adapters.permissions import RobotsDecision

_spec = importlib.util.spec_from_file_location(
    "mtk_verification_main", Path(__file__).resolve().parents[1] / "main.py")
worker_main = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = worker_main
_spec.loader.exec_module(worker_main)

URL = "https://example.com/terms"
TEXT = "Public documentation. " * 150 + "Use code SAVE2026 at checkout for students only."
SOURCE = {
    "id": "source-1", "provider": "Acme", "canonical_domain": "example.com",
    "adapter": "page_watch", "enabled": True, "trust_tier": "A_provider_owned",
    "config": {"url": URL},
}
OFFER = {"id": "offer-1", "provider": "Acme", "state": "evidence_needed"}


def allow_robots(monkeypatch, *, allowed=True):
    """Stub the per-host robots check; no network in these tests."""
    decision = RobotsDecision(
        domain="example.com", robots_url="https://example.com/robots.txt",
        checked_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
        allowed=allowed, status=200,
        reason="robots.txt permits this fetch" if allowed
        else "robots.txt disallows this fetch",
    )
    monkeypatch.setattr(worker_main, "check_robots", lambda domain, **kwargs: decision)
    return decision


def exercise(monkeypatch, *, complete=True, evidence_status=201, final_url=URL, sources=None,
             extra=None, robots_allowed=True, text=TEXT, extract_fn=None):
    posts, fetched = [], []
    sources = sources or [SOURCE]
    allow_robots(monkeypatch, allowed=robots_allowed)

    def fetch(url, fetcher=None, max_text_chars=2000, policy=None, **kwargs):
        fetched.append((url, max_text_chars))
        return [RawItem(external_item_id="snapshot-1", url=final_url, text=text,
                        extra=extra or {})]

    def transport(request):
        if request.method == "GET":
            assert request.url.path == "/sources"
            return httpx.Response(200, json=sources)
        payload = json.loads(request.content)
        posts.append((request.url.path, payload))
        if request.url.path.endswith("/evidence"):
            return httpx.Response(evidence_status, json={"id": "evidence-1", "duplicate": True})
        if request.url.path.endswith("/extraction"):
            return httpx.Response(201, json={"complete": complete})
        return httpx.Response(200, json={"state": payload.get("to")})

    monkeypatch.setattr(worker_main, "fetch_page_snapshot", fetch)
    if extract_fn is None:
        monkeypatch.setattr(worker_main, "extract_document", lambda section_text, url: (
            {
                "promo_code": {"value": "SAVE2026", "evidence_url": url,
                               "excerpt": section_text[-60:]},
                "eligibility": {"value": "students", "evidence_url": url,
                                "excerpt": section_text[-60:]},
            }, [], None, 1,
        ))
    else:
        monkeypatch.setattr(worker_main, "extract_document", extract_fn)
    worker = object.__new__(worker_main.Verifier)
    worker.api_url = "https://api.test"
    worker.fetcher = object()
    worker.policy = EgressPolicy()
    with httpx.Client(transport=httpx.MockTransport(transport)) as worker.client:
        worker.verify_offer(OFFER, build_allowlist(sources))
    return fetched, posts


def test_single_untruncated_snapshot_and_bound_evidence_id(monkeypatch):
    fetched, posts = exercise(monkeypatch)
    assert fetched == [(URL, None)]
    evidence, extraction, transition = [payload for _, payload in posts]
    assert len(TEXT) > 2000 and evidence["captured_content"] == TEXT
    assert evidence["supported_fields"] == ["eligibility", "promo_code"]
    assert extraction["fields"]["promo_code"]["evidence_id"] == "evidence-1"
    assert "complete" not in extraction
    assert transition["to"] == "verified"
    # WP01 slice 8: the extractor reports what it examined; the API re-derives it.
    assert extraction["coverage"] == {
        "version": "paragraph-groups/1",
        "sections_total": 1,
        "max_section_chars": 6000,
        "evidence_ids": ["evidence-1"],
    }


def test_long_document_is_sectioned_not_refused(monkeypatch):
    long_text = "Conditions apply to students only. Use code SAVE2026 at checkout.\n\n" * 8000
    assert len(long_text) > 250_000
    _, posts = exercise(monkeypatch, text=long_text, extract_fn=worker_main.extract_document)
    evidence = posts[0][1]
    extraction = posts[1][1]
    assert evidence["captured_content"] == long_text
    from document_sections import split_sections
    assert extraction["coverage"]["sections_total"] == len(split_sections(long_text))
    assert extraction["coverage"]["sections_total"] > 1


def test_document_above_the_ceiling_is_refused(monkeypatch):
    huge = "x" * (worker_main.MAX_DOCUMENT_CHARS + 1)
    with pytest.raises(ValueError, match="sectioned-processing ceiling"):
        exercise(monkeypatch, text=huge)


def test_server_incomplete_result_never_promotes(monkeypatch):
    _, posts = exercise(monkeypatch, complete=False)
    assert not any(path.endswith("/transition") for path, _ in posts)


def test_failed_snapshot_persistence_aborts_extraction(monkeypatch):
    with pytest.raises(httpx.HTTPStatusError):
        exercise(monkeypatch, evidence_status=422)


def test_official_redirect_outside_allowlist_aborts(monkeypatch):
    with pytest.raises(ValueError, match="redirected"):
        exercise(monkeypatch, final_url="https://evil.test/promo")


def test_disabled_source_is_not_fetched(monkeypatch):
    fetched, posts = exercise(monkeypatch, sources=[{**SOURCE, "enabled": False}])
    assert fetched == [] and posts == []


def test_provenance_and_raw_bytes_are_forwarded_to_the_api(monkeypatch):
    provenance = {
        "requested_url": URL, "final_url": URL, "http_status": 200,
        "content_type": "text/html", "fetched_at": "2026-10-21T12:00:00+00:00",
        "redirects": [], "raw_sha256": "a" * 64, "byte_length": 10,
        "encoding": "utf-8", "parser_version": "page_watch/1",
    }
    _, posts = exercise(monkeypatch, extra={
        "provenance": provenance, "raw_content_b64": "PGh0bWw+",
    })
    evidence = next(payload for path, payload in posts if path.endswith("/evidence"))
    assert evidence["raw_content_b64"] == "PGh0bWw+"
    assert evidence["provenance"]["parser_version"] == "page_watch/1"
    assert evidence["provenance"]["fetch_identity"] == worker_main.FETCH_IDENTITY
    assert evidence["provenance"]["robots"] == {
        "robots_url": "https://example.com/robots.txt",
        "checked_at": "2026-10-21T00:00:00+00:00",
        "allowed": True,
        "status": 200,
    }


def test_robots_refusal_prevents_the_fetch_and_the_evidence(monkeypatch):
    """No permission, no page, no evidence — even if the page would parse."""
    fetched, posts = exercise(monkeypatch, robots_allowed=False)
    assert fetched == [] and posts == []


def test_robots_is_checked_once_per_host(monkeypatch):
    calls = []

    def check(domain, **kwargs):
        calls.append(domain)
        return RobotsDecision(
            domain=domain, robots_url=f"https://{domain}/robots.txt",
            checked_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
            allowed=True, status=200, reason="robots.txt permits this fetch",
        )

    monkeypatch.setattr(worker_main, "check_robots", check)
    worker = object.__new__(worker_main.Verifier)
    worker.fetcher = object()
    worker.policy = EgressPolicy()
    first = worker._permission("https://example.com/a")
    second = worker._permission("https://example.com/b")
    assert first is second
    assert calls == ["example.com"]


def test_provenance_is_signed_with_the_deployment_key(monkeypatch):
    from fetch_attestation import verify_provenance

    key = "k" * 40
    monkeypatch.setattr(worker_main, "FETCH_SIGNING_KEY", key)
    provenance = {
        "requested_url": URL, "final_url": URL, "http_status": 200,
        "content_type": "text/html", "fetched_at": "2026-10-21T12:00:00+00:00",
        "redirects": [], "raw_sha256": "a" * 64, "byte_length": 10,
        "encoding": "utf-8", "parser_version": "page_watch/1",
    }
    _, posts = exercise(monkeypatch, extra={
        "provenance": provenance, "raw_content_b64": "PGh0bWw+",
    })
    evidence = next(payload for path, payload in posts if path.endswith("/evidence"))
    sent = evidence["provenance"]
    assert len(sent["signature"]) == 64
    assert verify_provenance(sent, sent["signature"], key) is True
    # Any post-signature edit invalidates it.
    assert verify_provenance(
        {**sent, "raw_sha256": "b" * 64}, sent["signature"], key,
    ) is False


def test_unsigned_provenance_is_forwarded_when_no_key_is_configured(monkeypatch):
    monkeypatch.setattr(worker_main, "FETCH_SIGNING_KEY", "")
    provenance = {
        "requested_url": URL, "final_url": URL, "http_status": 200,
        "content_type": "text/html", "fetched_at": "2026-10-21T12:00:00+00:00",
        "redirects": [], "raw_sha256": "a" * 64, "byte_length": 10,
        "encoding": "utf-8", "parser_version": "page_watch/1",
    }
    _, posts = exercise(monkeypatch, extra={
        "provenance": provenance, "raw_content_b64": "PGh0bWw+",
    })
    evidence = next(payload for path, payload in posts if path.endswith("/evidence"))
    # The worker does not invent a signature; the API rejects the record.
    assert "signature" not in evidence["provenance"]


def test_unavailable_page_is_not_stored_as_terms(monkeypatch):
    """A 503/challenge body must never become official evidence."""
    _, posts = exercise(monkeypatch, extra={
        "provenance": {
            "requested_url": URL, "final_url": URL, "http_status": 503,
            "content_type": "text/html", "fetched_at": "2026-10-21T12:00:00+00:00",
            "redirects": [], "raw_sha256": "a" * 64, "byte_length": 10,
            "encoding": "utf-8", "parser_version": "page_watch/1",
        },
        "raw_content_b64": "PGh0bWw+",
    })
    assert not any(path.endswith("/evidence") for path, _ in posts)
    assert not any(path.endswith("/extraction") for path, _ in posts)
    assert not any(path.endswith("/transition") for path, _ in posts)


def test_verification_fetch_uses_the_egress_policy(monkeypatch):
    seen = {}

    def fetch(url, fetcher=None, max_text_chars=2000, policy=None, **kwargs):
        seen["policy"] = policy
        return [RawItem(external_item_id="s", url=URL, text=TEXT)]

    monkeypatch.setattr(worker_main, "fetch_page_snapshot", fetch)
    monkeypatch.setattr(worker_main, "extract_document", lambda text, url: ({}, [], None, 1))
    allow_robots(monkeypatch)
    posts = []

    def post(path, json):
        posts.append(path)
        return httpx.Response(201, json={"id": "evidence-1", "complete": False},
                              request=httpx.Request("POST", "https://api.test" + path))

    worker = object.__new__(worker_main.Verifier)
    worker.fetcher = object()
    worker.policy = EgressPolicy()
    worker._official_pages = lambda *args: [URL]
    worker._post = post
    worker.verify_offer(OFFER, build_allowlist([SOURCE]))
    assert isinstance(seen["policy"], EgressPolicy)


def test_page_adapter_retains_footer_and_final_url():
    class Fetcher:
        def fetch(self, url, *, headers=None, params=None):
            return httpx.Response(
                200, text="<p>" + "public text " * 300 + "</p><footer>Students only.</footer>",
                request=httpx.Request("GET", URL + "/redirected"),
            )

        def fetch_policy(self, url, *, headers=None, params=None, policy=None):
            return self.fetch(url, headers=headers, params=params)
    full = fetch_page_snapshot(URL, fetcher=Fetcher(), max_text_chars=None)[0]
    excerpt = fetch_page_snapshot(URL, fetcher=Fetcher())[0]
    assert full.text.endswith("Students only.") and len(full.text) > 2000
    assert full.url == URL + "/redirected"
    assert len(excerpt.text) == 2000


def test_conflict_is_retained_when_best_page_lacks_that_field(monkeypatch):
    pages = [URL, URL + "/second", URL + "/third"]
    proposals = [
        {"expiry": {"value": "2026-12-01"}},
        {"promo_code": {"value": "SAVE2026"}, "eligibility": {"value": "students"}},
        {"expiry": {"value": "2027-01-01"}},
    ]
    posts = []

    def post(path, json):
        posts.append((path, json))
        return httpx.Response(201, json={"id": "evidence-1", "complete": False},
                              request=httpx.Request("POST", "https://api.test" + path))

    monkeypatch.setattr(worker_main, "fetch_page_snapshot", lambda url, **kwargs: [
        RawItem(external_item_id=url, url=url, text="Official terms")])
    monkeypatch.setattr(worker_main, "extract_document", lambda text, url: (
        proposals[pages.index(url)], [], None, 1))
    allow_robots(monkeypatch)
    worker = object.__new__(worker_main.Verifier)
    worker.fetcher = object()
    worker.policy = EgressPolicy()
    worker._official_pages = lambda *args: pages
    worker._post = post
    worker.verify_offer(OFFER, build_allowlist([SOURCE]))
    extraction = next(payload for path, payload in posts if path.endswith("/extraction"))
    assert any(conflict["field"] == "expiry" for conflict in extraction["conflicts"])
    assert not any(path.endswith("/transition") for path, _ in posts)
