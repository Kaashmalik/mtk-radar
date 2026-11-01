"""Test environment for the API package.

Sets the fetch-provenance signing key **before** the API is imported, so every
machine-evidence test signs its provenance exactly as the worker does. The key is
a fixed test value, never a deployment secret.

Also opts the test suite into dev-open mode explicitly: the API refuses to
boot without credentials unless MTK_ALLOW_UNAUTHENTICATED=1 is set (the
fail-closed startup guard). The tests are that sealed local environment —
the standalone hardening tests exercise the guard both ways.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault(
    "MTK_FETCH_SIGNING_KEY",
    "test-signing-key-0123456789abcdef0123456789abcdef",
)

# Fail-closed startup guard (P0-1): tests ARE the dev-open environment —
# unauthenticated + body-supplied reviewer names — which is only allowed with
# this explicit opt-in. setdefault so an operator's env is never overridden.
os.environ.setdefault("MTK_ALLOW_UNAUTHENTICATED", "1")
