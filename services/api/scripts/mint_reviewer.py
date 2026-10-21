"""Reviewer identity management (v0.16) — mint, list, and revoke personal API
tokens (reviewers table, sha256 at rest; plaintext shown exactly once).

Run:  python -m scripts.mint_reviewer --name Kashi    (from services/api/, DATABASE_URL set)
      docker compose exec api python -m scripts.mint_reviewer --name Kashi

The token authenticates the dashboard and API calls as that reviewer
(`Authorization: Bearer <token>`); audit_log.actor and reviewer fields bind to
the token owner server-side. Workers keep using the shared MTK_API_TOKEN.
"""

import argparse
import asyncio
import os
import secrets
import sys

import asyncpg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_hardening import token_hash  # noqa: E402

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://mtk:mtk@localhost:5432/mtk_radar")


async def mint(name: str) -> None:
    token = secrets.token_urlsafe(32)
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            """
            INSERT INTO reviewers (name, token_hash) VALUES ($1, $2)
            ON CONFLICT (name) DO UPDATE SET token_hash = EXCLUDED.token_hash, active = TRUE
            """,
            name, token_hash(token),
        )
    finally:
        await conn.close()
    print(f"reviewer token for '{name}' (stored hashed; shown exactly once):")
    print(token)
    print("\nUse in the dashboard: paste it under Identity. Use in scripts:")
    print(f"  curl -H 'Authorization: Bearer <token>' $API_URL/whoami")


async def revoke(name: str) -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        n = await conn.execute("UPDATE reviewers SET active = FALSE WHERE name = $1", name)
    finally:
        await conn.close()
    print(f"revoked '{name}' ({n}) — takes effect on the reviewer's next request")


async def list_reviewers() -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch(
            "SELECT name, active, created_at FROM reviewers ORDER BY name"
        )
    finally:
        await conn.close()
    for r in rows:
        print(f"{'ACTIVE  ' if r['active'] else 'REVOKED '} {r['name']}  (since {r['created_at']:%Y-%m-%d})")
    if not rows:
        print("no reviewers yet — mint one: python -m scripts.mint_reviewer --name Kashi")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name", help="reviewer name to mint (or re-mint — old token is replaced)")
    ap.add_argument("--revoke", help="reviewer name to revoke")
    ap.add_argument("--list", action="store_true", help="list reviewers")
    args = ap.parse_args()

    if args.list:
        asyncio.run(list_reviewers())
    elif args.revoke:
        asyncio.run(revoke(args.revoke))
    elif args.name:
        if len(args.name) < 2:
            ap.error("--name must be at least 2 characters")
        asyncio.run(mint(args.name))
    else:
        ap.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
