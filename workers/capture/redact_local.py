"""Slim local copy of the API's secret scanner for offline use in the capture
worker. No network needed; pattern values never leave this machine.

Keep in sync with services/api/redact.py.
"""

import re
from typing import Final

SECRET_PATTERNS: Final[dict[str, re.Pattern]] = {
    "openai_style_key": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github_pat": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "slack_token": re.compile(r"\bxox[abp]-[A-Za-z0-9-]{10,}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    "private_key_block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "password_assignment": re.compile(r"(?i)\b(password|passwd|pwd|secret|token|recovery.?code)\b\s*[:=]\s*\S+"),
    "api_key_assignment": re.compile(r"(?i)\bapi[_-]?key\b\s*[:=]\s*\S+"),
    "long_hex_secret": re.compile(r"\b[a-fA-F0-9]{40,}\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
}


def scan(text: str) -> list[dict]:
    findings = []
    for name, pattern in SECRET_PATTERNS.items():
        count = len(pattern.findall(text or ""))
        if count:
            findings.append({"pattern": name, "count": count})
    return findings


def redact(text: str) -> str:
    result = text or ""
    for name, pattern in SECRET_PATTERNS.items():
        result = pattern.sub(f"[REDACTED:{name}]", result)
    return result
