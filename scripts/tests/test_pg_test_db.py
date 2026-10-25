"""URL/name handling for the external-Postgres verification helper."""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import pg_test_db  # noqa: E402


def test_with_database_preserves_credentials_host_port_and_query():
    base = "postgresql://mtk:secret@127.0.0.1:55499/mtk_verify?sslmode=disable"
    assert pg_test_db.with_database(base, "mtk_verify_e2e") == (
        "postgresql://mtk:secret@127.0.0.1:55499/mtk_verify_e2e?sslmode=disable")


def test_admin_url_uses_postgres_database():
    base = "postgresql://mtk@127.0.0.1:55499/mtk_verify"
    assert pg_test_db.with_database(base, "postgres").endswith("/postgres")


@pytest.mark.parametrize("name", ["bad-name", "x; DROP DATABASE y", "", "9start"])
def test_unsafe_database_names_are_rejected(name):
    with pytest.raises(ValueError):
        pg_test_db.with_database("postgresql://mtk@127.0.0.1/mtk_verify", name)
