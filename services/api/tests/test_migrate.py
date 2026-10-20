"""Migration runner policy tests (pure — no database needed)."""

import pytest

from db_migrate import check_sequence, migration_files, pending, sort_key, valid_name
from pathlib import Path


def _fake(name: str) -> Path:
    return Path(name)


class TestNaming:
    def test_valid_names(self):
        assert valid_name("001_init.sql")
        assert valid_name("007_corrections_expiry.sql")
        assert not valid_name("1_init.sql")
        assert not valid_name("001-init.sql")
        assert not valid_name("readme.sql")

    def test_sort_key_uses_prefix(self):
        assert sort_key(_fake("002_b.sql")) < sort_key(_fake("010_a.sql"))


class TestSequence:
    def test_ok(self):
        check_sequence([_fake(f"{i:03d}_x.sql") for i in range(1, 5)])

    def test_gap_refuses(self):
        with pytest.raises(ValueError):
            check_sequence([_fake("001_a.sql"), _fake("003_c.sql")])


class TestPending:
    def test_pending_filters_applied_keeps_order(self):
        files = [_fake("001_a.sql"), _fake("002_b.sql"), _fake("003_c.sql")]
        assert pending({"002_b.sql"}, files) == [_fake("001_a.sql"), _fake("003_c.sql")]
        assert pending(set(), files) == files
        assert pending({"001_a.sql", "002_b.sql", "003_c.sql"}, files) == []


class TestRealMigrations:
    def test_repo_migrations_well_formed_and_sequential(self):
        files = migration_files()
        assert len(files) >= 7
        check_sequence(files)  # raises on a gap in the real repo

    def test_pending_is_first_order(self):
        # never applied → everything is pending, in canonical order
        names = [p.name for p in pending(set(), migration_files())]
        assert names == sorted(names)
