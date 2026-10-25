#!/usr/bin/env python3
"""Create a disposable PostgreSQL database on an existing server.

The verification script normally starts Docker's postgres:16-alpine. On hosts
without a Docker daemon (for example a Windows workstation running portable
PostgreSQL), operators can supply ``MTK_VERIFY_DATABASE_URL`` instead. This
helper recreates the E2E database on that server and prints its DSN.

The target name is validated and quoted; this is a test utility, not a
general-purpose administration tool. Never point it at a database you care
about: the named database is dropped first.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from urllib.parse import urlsplit, urlunsplit

import asyncpg

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def with_database(base_url: str, name: str) -> str:
    if not _NAME.fullmatch(name):
        raise ValueError(f"unsafe database name: {name!r}")
    parts = urlsplit(base_url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{name}",
                       parts.query, parts.fragment))


async def recreate(base_url: str, name: str) -> str:
    target = with_database(base_url, name)
    admin_url = with_database(base_url, "postgres")
    conn = await asyncpg.connect(admin_url)
    try:
        quoted = '"' + name.replace('"', '""') + '"'
        await conn.execute(f"DROP DATABASE IF EXISTS {quoted} WITH (FORCE)")
        await conn.execute(f"CREATE DATABASE {quoted}")
    finally:
        await conn.close()
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Recreate a disposable database on an existing PostgreSQL.")
    parser.add_argument("--base-url", required=True,
                        help="DSN on the same server (any database; admin DB is derived)")
    parser.add_argument("--name", required=True,
                        help="disposable database name to recreate")
    args = parser.parse_args(argv)
    try:
        print(asyncio.run(recreate(args.base_url, args.name)))
    except Exception as exc:  # noqa: BLE001 - CLI surfaces a clear failure
        print(f"pg_test_db: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
