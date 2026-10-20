"""Unit tests for dedup primitives (services/api/normalize.py)."""

from normalize import canonicalize_url, hash_parts, normalize_text, text_hash


class TestCanonicalizeUrl:
    def test_strips_www_and_trailing_slash(self):
        assert (
            canonicalize_url("https://www.example.com/blog/post/")
            == "https://example.com/blog/post"
        )

    def test_removes_tracking_params(self):
        url = canonicalize_url(
            "https://example.com/deal?utm_source=x&fbclid=abc&id=7"
        )
        assert url == "https://example.com/deal?id=7"

    def test_drops_fragment(self):
        assert canonicalize_url("https://example.com/a#section") == "https://example.com/a"

    def test_lowercases_host(self):
        assert canonicalize_url("https://GitHub.COM/ollama/ollama/releases") == (
            "https://github.com/ollama/ollama/releases"
        )

    def test_keeps_nondefault_port(self):
        assert canonicalize_url("http://example.com:8080/x") == "http://example.com:8080/x"

    def test_drops_default_port(self):
        assert canonicalize_url("https://example.com:443/x") == "https://example.com/x"

    def test_root_stays_root(self):
        assert canonicalize_url("https://example.com/") == "https://example.com/"

    def test_identical_pages_collapse(self):
        a = canonicalize_url("https://www.get.tech/promo?utm_campaign=fall")
        b = canonicalize_url("https://get.tech/promo/#top")
        assert a == b


class TestHashing:
    def test_whitespace_insensitive(self):
        assert text_hash("Free  Credits  for students") == text_hash("free credits for students")

    def test_none_parts_ignored(self):
        assert hash_parts("url", None, "title") == hash_parts("url", "title")

    def test_different_input_different_hash(self):
        assert text_hash("a") != text_hash("b")

    def test_normalize_len(self):
        assert normalize_text(None, "") == ""
