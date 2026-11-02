"""Evidence recorder: counts are parsed from real verify output and a
database password never reaches a committed file."""

from record_verify_evidence import _redact, summarize

SAMPLE = """
▸ Filename portability
✔ filenames portable
▸ Unit + integration tests
1210 passed, 4 skipped, 55 warnings in 140.2s
✔ tests green
# pass 29
9 passed (33.1s)
"""


def test_summary_counts_python_extension_and_playwright():
    checks = summarize(SAMPLE)
    assert checks["python_tests"] == {"passed": 1210, "skipped": 4, "failed": 0}
    assert checks["playwright"] == {"passed": 9}
    assert checks["extension_node_tests"] == 29
    assert checks["steps_ok"] == ["filenames portable", "tests green"]
    assert "failed_step" not in checks


def test_failed_step_is_recorded():
    assert summarize("✘ dashboard build\n")["failed_step"] == "dashboard build"


def test_database_password_is_redacted():
    assert _redact("postgresql://mtk:s3cret@127.0.0.1:55499/postgres") == \
        "postgresql://mtk:***@127.0.0.1:55499/postgres"
    assert _redact("postgresql://mtk@127.0.0.1/postgres") == "postgresql://mtk@127.0.0.1/postgres"
