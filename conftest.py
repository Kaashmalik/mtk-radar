"""Repository-wide test isolation.

Workers spool undeliverable telemetry/notifications to a durable outbox
(packages/outbox). Tests must never write into the developer's real outbox
under the home directory, so every test gets a private one.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolated_outbox(tmp_path, monkeypatch):
    monkeypatch.setenv("MTK_OUTBOX_DIR", str(tmp_path / "outbox"))
