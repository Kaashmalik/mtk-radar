"""Redaction scanner tests — patterns detected, values never persisted."""

from redact import is_clean, redact, scan

SECRET_SAMPLE = (
    "export OPENAI_API_KEY=sk-abc123def456ghi789jkl012\n"
    "aws_key AKIAIOSFODNN7EXAMPLE\n"
    "github ghp_0123456789abcdefghijklmnopqrstuvwxyzAB\n"
    "token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U\n"
)


class TestScan:
    def test_detects_openai_key(self):
        assert {"pattern": "openai_style_key", "count": 1} in scan(SECRET_SAMPLE)

    def test_detects_aws_key(self):
        assert {"pattern": "aws_access_key", "count": 1} in scan(SECRET_SAMPLE)

    def test_detects_github_pat(self):
        assert {"pattern": "github_pat", "count": 1} in scan(SECRET_SAMPLE)

    def test_detects_jwt(self):
        assert {"pattern": "jwt", "count": 1} in scan(SECRET_SAMPLE)

    def test_detects_password_assignment(self):
        assert any(f["pattern"] == "password_assignment" for f in scan("password=hunter2"))

    def test_detects_email(self):
        assert any(f["pattern"] == "email" for f in scan("contact kashif@example.com"))

    def test_detects_private_key_block(self):
        assert any(f["pattern"] == "private_key_block" for f in scan("-----BEGIN RSA PRIVATE KEY-----"))

    def test_clean_text_has_no_findings(self):
        assert scan("free .tech domain for students, offer ends January 31, 2027") == []
        assert is_clean("nothing sensitive here")

    def test_findings_never_contain_values(self):
        # The core safety property: findings are pattern names + counts only.
        for finding in scan(SECRET_SAMPLE):
            assert set(finding) == {"pattern", "count"}


class TestRedact:
    def test_masks_secret(self):
        masked = redact("key is sk-abc123def456ghi789jkl012 ok")
        assert "sk-abc123" not in masked
        assert "[REDACTED:openai_style_key]" in masked

    def test_masks_email(self):
        masked = redact("mail me at kashif@example.com")
        assert "kashif@example.com" not in masked
        assert "[REDACTED:email]" in masked

    def test_idempotent_on_clean_text(self):
        clean = "offer ends 2027-01-31, $49.99 renewal"
        assert redact(clean) == clean
