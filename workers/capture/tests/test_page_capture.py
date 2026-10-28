"""Public-page capture worker (M2) — policy and job flow, no browser/network."""

from types import SimpleNamespace

import pytest

import page_capture as pc
from source_adapters.egress import EgressPolicy


def _resolver(table):
    def resolve(host, port):
        return table[host]
    return resolve


PUBLIC = {"example.org": ["93.184.215.14"], "cdn.example.org": ["93.184.215.15"],
          "intranet.local": ["10.0.0.5"], "metadata.internal": ["169.254.169.254"]}


def test_host_guard_blocks_private_and_metadata_hosts():
    guard = pc.HostGuard(resolver=_resolver(PUBLIC))
    assert guard.allows("https://example.org/paper")
    assert guard.allows("https://cdn.example.org/app.js")
    assert not guard.allows("https://intranet.local/admin")
    assert not guard.allows("http://metadata.internal/latest/meta-data")
    assert not guard.allows("https://127.0.0.1/")
    assert not guard.allows("file:///etc/passwd")
    assert guard.allows("data:image/png;base64,AAAA"), "inline resources need no network"


def test_robots_semantics():
    rules = "User-agent: MTK-Radar-PageCapture\nDisallow: /private\n"
    assert pc.robots_allows(rules, "https://example.org/paper", 200)
    assert not pc.robots_allows(rules, "https://example.org/private/x", 200)
    assert pc.robots_allows(None, "https://example.org/x", 404), "no robots file = allowed"
    assert not pc.robots_allows(None, "https://example.org/x", 503), "server error = disallow"
    assert not pc.robots_allows(None, "https://example.org/x", None), "unreachable = disallow"
    assert pc.robots_url("https://example.org/a/b?c=1") == "https://example.org/robots.txt"


def _fetch(status, body=b""):
    def fetch(url, policy, headers):
        assert url.endswith("/robots.txt")
        return SimpleNamespace(status=status, body=body)
    return fetch


def test_preflight_refuses_bad_urls_private_hosts_and_robots():
    guard = pc.HostGuard(resolver=_resolver(PUBLIC))
    policy = EgressPolicy()
    pc.preflight("https://example.org/paper", policy, guard, _fetch(404))
    with pytest.raises(pc.Refused, match="scheme"):
        pc.preflight("http://example.org/paper", policy, guard, _fetch(404))
    with pytest.raises(pc.Refused, match="credentials"):
        pc.preflight("https://user:pw@example.org/", policy, guard, _fetch(404))
    with pytest.raises(pc.Refused, match="public"):
        pc.preflight("https://intranet.local/", policy, guard, _fetch(404))
    with pytest.raises(pc.Refused, match="robots"):
        pc.preflight("https://example.org/x", policy, guard,
                     _fetch(200, b"User-agent: *\nDisallow: /\n"))


class FakeApi:
    def __init__(self, rows, claimed=True):
        self.rows, self.claimed, self.posts = rows, claimed, []

    def post(self, path, json=None):
        self.posts.append((path, json))
        if path == "/jobs/claim":
            if not self.claimed:
                return SimpleNamespace(status_code=200, json=lambda: {"claimed": False})
            self.claimed = False
            return SimpleNamespace(status_code=200, json=lambda: {
                "claimed": True, "id": "job-1", "entity_id": "offer-1",
                "payload": {"capture_ids": ["c1", "c2", "c3"]}})
        return SimpleNamespace(status_code=200, json=lambda: {})

    def get(self, path):
        return SimpleNamespace(status_code=200, json=lambda: self.rows)


def test_drain_reports_each_page_and_settles_the_job(tmp_path, monkeypatch):
    monkeypatch.delenv("MTK_STORAGE_BACKEND", raising=False)
    rows = [
        {"id": "c1", "url": "https://example.org/paper", "status": "requested"},
        {"id": "c2", "url": "https://intranet.local/", "status": "requested"},
        {"id": "c3", "url": "https://example.org/broken", "status": "requested"},
        {"id": "c4", "url": "https://example.org/other", "status": "requested"},  # not in job
    ]

    def fake_capture(url, guard):
        if url.endswith("broken"):
            raise TimeoutError("navigation timed out")
        return pc.Shot(url, "Paper title", 200, b"\x89PNG-bytes")

    worker = pc.Worker("http://api", tmp_path, guard=pc.HostGuard(resolver=_resolver(PUBLIC)),
                       capture_fn=fake_capture, fetch=_fetch(404))
    worker.api = FakeApi(rows)
    assert worker.drain() == 1
    results = {path.split("/")[2]: body for path, body in worker.api.posts
               if path.startswith("/page-captures/")}
    assert results["c1"]["status"] == "ok" and results["c1"]["title"] == "Paper title"
    assert len(results["c1"]["image_sha256"]) == 64
    assert (tmp_path / "offer-1" / "c1.png").read_bytes() == b"\x89PNG-bytes"
    assert results["c2"]["status"] == "refused"
    assert results["c3"]["status"] == "failed" and "timed out" in results["c3"]["detail"]
    assert "c4" not in results, "only the job's own captures are processed"
    job = [b for p, b in worker.api.posts if p == "/jobs/job-1/result"][0]
    assert job["ok"] is True and job["worker"] == worker.holder


class _FakePlaywright:
    """Just enough of sync_playwright to drive capture() deterministically."""

    def __init__(self, subrequests, final_url):
        self.subrequests, self.final_url = subrequests, final_url
        self.decisions, self.context_kwargs = {}, None

    def __call__(self):
        return self

    def __enter__(self):
        fake = self

        class Route:
            def __init__(self, url):
                self.request = SimpleNamespace(url=url)

            def continue_(self):
                fake.decisions[self.request.url] = "continue"

            def abort(self):
                fake.decisions[self.request.url] = "abort"

        class Page:
            url = fake.final_url

            def goto(self, url, wait_until, timeout):
                for sub in [url, *fake.subrequests]:
                    fake.handler(Route(sub))
                return SimpleNamespace(status=200)

            def wait_for_load_state(self, state, timeout):
                pass

            def screenshot(self, type, full_page):
                assert full_page is False
                return b"PNG"

            def title(self):
                return "A public page"

        class Context:
            def route(self, pattern, handler):
                fake.handler = handler

            def new_page(self):
                return Page()

            def close(self):
                pass

        class Browser:
            def new_context(self, **kwargs):
                fake.context_kwargs = kwargs
                return Context()

            def close(self):
                pass

        self.chromium = SimpleNamespace(launch=lambda **kw: Browser())
        return self

    def __exit__(self, *exc):
        return False


def test_capture_aborts_private_subrequests_in_a_fresh_sandboxed_context():
    guard = pc.HostGuard(resolver=_resolver(PUBLIC))
    fake = _FakePlaywright(["https://cdn.example.org/app.js",
                            "https://intranet.local/beacon",
                            "http://metadata.internal/latest"], "https://example.org/paper")
    shot = pc.capture("https://example.org/paper", guard, playwright_factory=fake)
    assert shot.png == b"PNG" and shot.title == "A public page" and shot.http_status == 200
    assert fake.decisions["https://cdn.example.org/app.js"] == "continue"
    assert fake.decisions["https://intranet.local/beacon"] == "abort"
    assert fake.decisions["http://metadata.internal/latest"] == "abort"
    kwargs = fake.context_kwargs
    assert kwargs["accept_downloads"] is False and kwargs["service_workers"] == "block"
    assert "storage_state" not in kwargs, "never a logged-in profile"


def test_redirect_to_a_private_host_is_refused():
    guard = pc.HostGuard(resolver=_resolver(PUBLIC))
    fake = _FakePlaywright([], "https://intranet.local/after-redirect")
    with pytest.raises(pc.Refused, match="non-public"):
        pc.capture("https://example.org/paper", guard, playwright_factory=fake)
