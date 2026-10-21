"""Test environment for the API package.

Sets the fetch-provenance signing key **before** the API is imported, so every
machine-evidence test signs its provenance exactly as the worker does. The key is
a fixed test value, never a deployment secret.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault(
    "MTK_FETCH_SIGNING_KEY",
    "test-signing-key-0123456789abcdef0123456789abcdef",
)
