"""Guard the test-discovery source of truth (pytest.ini CI note, plan §7).

CI, scripts/verify.sh and `pnpm test` all run bare `pytest`, so testpaths in
pytest.ini is the single discovery list. Two silent-failure modes existed:

1. a listed directory is deleted/renamed → pytest errors (loud, already fine);
2. a NEW tests/ directory is added but never listed → pytest skips it forever,
   and every runner agrees on the gap (silent).

This test makes mode 2 loud in every runner.
"""

import configparser
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _listed_paths() -> list[str]:
    parser = configparser.ConfigParser()
    parser.read(REPO / "pytest.ini")
    raw = parser["pytest"]["testpaths"]
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _actual_test_dirs() -> set[str]:
    """Every directory in the repo containing tests — not just the four roots
    KNOWN at the time this guard was written. A future `tools/` or `infra/`
    tree with tests must hit the same loud failure, or the guard re-opens the
    silent-skip mode it exists to prevent."""
    found: set[str] = set()
    for path in REPO.rglob("test_*.py"):
        parts = set(path.relative_to(REPO).parts)
        if parts & {".venv", "node_modules", ".git", "__pycache__"}:
            continue
        # conftest-only helper dirs and one-off scripts carry no tests dir;
        # the discovery unit is the directory containing the tests.
        found.add(str(path.parent.relative_to(REPO)))
    return found


def test_every_listed_testpath_exists_and_has_tests():
    listed = _listed_paths()
    assert listed, "pytest.ini must declare testpaths explicitly"
    for path in listed:
        directory = REPO / path
        assert directory.is_dir(), f"pytest.ini lists '{path}' but it does not exist"
        assert any(directory.glob("test_*.py")), (
            f"pytest.ini lists '{path}' but it contains no test_*.py files")


def test_every_test_directory_is_listed_in_pytest_ini():
    listed = {str(Path(p)) for p in _listed_paths()}
    missing = _actual_test_dirs() - listed
    assert not missing, (
        "test directories exist but are NOT in pytest.ini testpaths — pytest "
        "would skip them in every runner: " + ", ".join(sorted(missing))
    )
