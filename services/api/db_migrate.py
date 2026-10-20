"""Migration runner (week 12 — "set retention, backups, idempotency, and
migration policy early", master plan §13).

Policy:
- Migrations are numbered SQL files in services/api/db/migrations (001…NNN),
  applied strictly in filename order, each in its own transaction.
- Applied migrations are recorded in schema_migrations and never re-run.
- The docker-compose postgres container runs the same directory on first boot
  (docker-entrypoint-initdb.d), so this runner is for deploys that reuse an
  existing volume.

Usage:
    python services/api/db_migrate.py            # apply pending, print summary
    python -m pytest services/api/tests/test_migrate.py   # pure logic tests
"""

import asyncio
import os
import re
import sys
from pathlib import Path

# asyncpg is imported lazily in apply_all() so the pure policy helpers
# (naming/order/pending) stay testable without database deps installed.

MIGRATIONS_DIR = Path(__file__).resolve().parent / "db" / "migrations"
NAME_RE = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")

DATABASE_URL_DEFAULT = "postgresql://mtk:mtk@localhost:5432/mtk_radar"

REGISTRY_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  name       TEXT PRIMARY KEY,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def valid_name(name: str) -> bool:
    return bool(NAME_RE.match(name))


def sort_key(path: Path) -> tuple:
    """Zero-padded numeric prefix first; misnamed files fail loudly."""
    if not valid_name(path.name):
        raise ValueError(f"bad migration filename (want NNN_snake_name.sql): {path.name}")
    return (path.name[:3], path.name)


def migration_files(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    files = [p for p in directory.glob("*.sql") if p.name != "README.md"]
    return sorted(files, key=sort_key)


def pending(applied: set[str], files: list[Path] | None = None) -> list[Path]:
    """Files not yet applied, in order — the only decision the runner makes."""
    files = files if files is not None else migration_files()
    return [p for p in files if p.name not in applied]


def check_sequence(files: list[Path]) -> None:
    """Gaps indicate a renamed/lost migration — refuse to run (policy §13)."""
    numbers = [int(p.name[:3]) for p in files]
    expected = list(range(1, len(numbers) + 1))
    if numbers != expected:
        raise ValueError(f"migration numbering gap: {numbers} != {expected}")


async def apply_all(dsn: str, directory: Path = MIGRATIONS_DIR) -> dict:
    import asyncpg  # deferred: pure helpers above avoid the DB dependency

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(REGISTRY_DDL)
        applied = {r["name"] for r in await conn.fetch("SELECT name FROM schema_migrations")}
        files = migration_files(directory)
        check_sequence(files)

        ran: list[str] = []
        for path in files:
            if path.name in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (name) VALUES ($1)", path.name
                )
            ran.append(path.name)
        return {"applied": ran, "total_known": len(files)}
    finally:
        await conn.close()


def main() -> int:
    dsn = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
        "DATABASE_URL", DATABASE_URL_DEFAULT
    )
    summary = asyncio.run(apply_all(dsn))
    if summary["applied"]:
        print("Applied: " + ", ".join(summary["applied"]))
    else:
        print(f"Up to date ({summary['total_known']} migrations known).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
