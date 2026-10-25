"""CODE-08: a capped /attention response must say so.

The endpoint returns exact per-kind totals but at most `LIMIT_PER_KIND` rows
per kind. The dashboard and the monitor must be able to distinguish "50 open"
from "50 shown of 137 open".
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from attention_api import summarize_kind  # noqa: E402


def test_complete_list_is_not_flagged():
    assert summarize_kind(0, 0) == {
        "count": 0, "returned": 0, "truncated": False,
    }
    assert summarize_kind(50, 50) == {
        "count": 50, "returned": 50, "truncated": False,
    }


def test_capped_list_exposes_both_numbers():
    assert summarize_kind(137, 50) == {
        "count": 137, "returned": 50, "truncated": True,
    }
