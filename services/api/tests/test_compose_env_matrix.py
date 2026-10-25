"""G13 (EP-02): the Compose environment matrix is enforced, not folk wisdom.

A value documented in `.env.example` must not imply a container receives it:
before this guard, `VERIFY_LLM_*`, `TTS_*` and `COST_*` settings were
documented, read by code (`workers/verification/extractors.py`,
`workers/render/narration.py`, `services/api/costs_store.py`) — and silently
absent from every container, so deployment behavior differed from every local
run. The collector lacked the documented `REDIS_URL` cache; publishing lacked
the documented Instagram settings.

The MATRIX below is derived from the `os.environ` reads in the consuming
modules (each entry names its reader). Two directions are asserted:

1. every documented var with a listed consumer appears in that service's
   compose `environment`;
2. every `${VAR}` compose placeholder is documented in `.env.example` or on
   the explicit internal allowlist — nothing is configurable through the env
   file without being written down.
"""

from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[3]
COMPOSE = _REPO / "infra" / "docker" / "docker-compose.yml"
ENV_EXAMPLE = _REPO / ".env.example"

#: Var → services that READ it in code (consumer module noted). A service may
#: receive more than this; it may never receive less.
MATRIX: dict[str, tuple[str, ...]] = {
    # workers/verification/extractors.py (LLM extraction + hardening)
    "VERIFY_LLM_BASE_URL": ("api", "verification"),
    "VERIFY_LLM_API_KEY": ("api", "verification"),
    "VERIFY_LLM_MODEL": ("api", "verification"),
    "VERIFY_LLM_TIMEOUT_S": ("verification",),
    "VERIFY_LLM_MAX_ATTEMPTS": ("verification",),
    "VERIFY_LLM_MAX_CALLS_PER_RUN": ("verification",),
    # services/api/costs_store.py — builds every USD estimate + probe
    "COST_LLM_INPUT_PER_MTOK": ("api",),
    "COST_LLM_OUTPUT_PER_MTOK": ("api",),
    "COST_TTS_PER_MCHAR": ("api",),
    # workers/render/narration.py (+ per-language overrides) and the API probe
    "TTS_BASE_URL": ("api", "render"),
    "TTS_API_KEY": ("api", "render"),
    "TTS_MODEL": ("api", "render"),
    "TTS_VOICE": ("api", "render"),
    "TTS_BASE_URL_UR": ("render",),
    "TTS_API_KEY_UR": ("render",),
    "TTS_MODEL_UR": ("render",),
    "TTS_VOICE_UR": ("render",),
    # packages/source_adapters/trendcache.py — the collectors' shared cache
    "REDIS_URL": ("api", "collectors"),
    # workers/publishing/main.py (dynamic <PREFIX>_) + workers/metrics/main.py
    "INSTAGRAM_USER_ID": ("publishing", "metrics"),    "INSTAGRAM_ACCESS_TOKEN": ("publishing", "metrics"),
    # workers/publishing/main.py (public media URL + WP-G token refresh)
    "MTK_PUBLIC_MEDIA_BASE_URL": ("publishing",),
    "MTK_TOKEN_REFRESH_CADENCE_D": ("publishing",),
    "MTK_TOKEN_REFRESH_MARGIN_D": ("publishing",),
    "FACEBOOK_APP_ID": ("publishing",),
    "FACEBOOK_APP_SECRET": ("publishing",),
}

#: Compose names that are intentionally compose-internal: interpolated from
#: other values, service-to-service addressing, or image conventions not
#: operator configuration (and therefore not .env.example documentation).
INTERNAL = {
    "DATABASE_URL",          # built from POSTGRES_PASSWORD inside compose
    "API_URL",               # service DNS name (documented for dev only)
    "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
    "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD",
    "NODE_ENV",
    "MTK_S3_ENDPOINT",       # in .env.example, but the compose default is
    "MTK_S3_BUCKET",         # service addressing; kept here as belt+braces
    "MTK_S3_ACCESS_KEY", "MTK_S3_SECRET_KEY", "MTK_S3_REGION",
    "MTK_STORAGE_LOCAL_ROOT", "MTK_STORAGE_CACHE",
    "MTK_FETCH_IDENTITY",    # worker self-label, not an operator setting
    "MTK_WORKER_HEARTBEATS",
}


@pytest.fixture(scope="module")
def compose_env() -> dict[str, dict[str, str]]:
    doc = yaml.safe_load(COMPOSE.read_text())
    out: dict[str, dict[str, str]] = {}
    for name, svc in (doc.get("services") or {}).items():
        env = svc.get("environment") or {}
        if isinstance(env, list):  # list form: KEY=VALUE
            env = dict(e.split("=", 1) for e in env)
        out[name] = env
    return out


@pytest.fixture(scope="module")
def documented() -> set[str]:
    names: set[str] = set()
    for line in ENV_EXAMPLE.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            stripped = stripped.lstrip("#").strip()
        if "=" in stripped and not stripped.startswith("#"):
            names.add(stripped.split("=", 1)[0].strip())
    return names


def test_every_documented_consumer_receives_its_vars(compose_env):
    """Direction 1: documented var → its consuming containers receive it."""
    missing = []
    for var, services in MATRIX.items():
        for svc in services:
            assert svc in compose_env, f"matrix names unknown service {svc!r}"
            if var not in compose_env[svc]:
                missing.append(f"{svc}: {var}")
    assert not missing, (
        "documented settings never reach their consumers: " + ", ".join(missing))


def test_every_compose_placeholder_is_documented_or_internal(compose_env, documented):
    """Direction 2: a container env name must be documented in .env.example OR
    compose-internal — a bare name in compose that resolves via the host shell
    is invisible configuration."""
    problems = []
    for svc, env in compose_env.items():
        for key, value in env.items():
            if key in INTERNAL or key in documented:
                continue
            # Interpolated placeholders inside values must also be written down.
            import re

            for ref in re.findall(r"\$\{([^:}]+)", str(value)):
                if ref not in documented and ref not in INTERNAL:
                    problems.append(f"{svc}: {key} interpolates undeclared {ref}")
            problems.append(f"{svc}: {key} is neither documented nor internal")
    assert not problems, "undeclared compose configuration: " + "; ".join(problems)


def test_matrix_matches_the_consumers_in_code():
    """The matrix itself cannot rot silently: each var must still be READ by
    the named consumer's code (otherwise the entry is stale and belongs here
    not in compose).

    CODE-11: this used to spot-check 7 of the 25 vars. The mapping below covers
    every entry, and the last assertion makes a newly added matrix var fail
    until its reader is named.
    """
    readers = {
        "VERIFY_LLM_BASE_URL": ["workers/verification/extractors.py",
                                "services/api/costs_store.py"],
        "VERIFY_LLM_API_KEY": ["workers/verification/extractors.py"],
        "VERIFY_LLM_MODEL": ["workers/verification/extractors.py"],
        "VERIFY_LLM_TIMEOUT_S": ["workers/verification/extractors.py"],
        "VERIFY_LLM_MAX_ATTEMPTS": ["workers/verification/extractors.py"],
        "VERIFY_LLM_MAX_CALLS_PER_RUN": ["workers/verification/extractors.py"],
        "COST_LLM_INPUT_PER_MTOK": ["services/api/costs_store.py"],
        "COST_LLM_OUTPUT_PER_MTOK": ["services/api/costs_store.py"],
        "COST_TTS_PER_MCHAR": ["services/api/costs_store.py"],
        "TTS_BASE_URL": ["workers/render/narration.py",
                         "services/api/costs_store.py"],
        "TTS_API_KEY": ["workers/render/narration.py"],
        "TTS_MODEL": ["workers/render/narration.py"],
        "TTS_VOICE": ["workers/render/narration.py"],
        "TTS_BASE_URL_UR": ["workers/render/narration.py"],
        "TTS_API_KEY_UR": ["workers/render/narration.py"],
        "TTS_MODEL_UR": ["workers/render/narration.py"],
        "TTS_VOICE_UR": ["workers/render/narration.py"],
        "REDIS_URL": ["packages/source_adapters/trendcache.py"],
        "INSTAGRAM_USER_ID": ["workers/publishing/main.py",
                              "workers/metrics/main.py"],
        "INSTAGRAM_ACCESS_TOKEN": ["workers/publishing/main.py",
                                   "workers/metrics/main.py"],
        "MTK_PUBLIC_MEDIA_BASE_URL": ["workers/publishing/main.py"],
        "MTK_TOKEN_REFRESH_CADENCE_D": ["workers/publishing/main.py"],
        "MTK_TOKEN_REFRESH_MARGIN_D": ["workers/publishing/main.py"],
        "FACEBOOK_APP_ID": ["workers/publishing/main.py"],
        "FACEBOOK_APP_SECRET": ["workers/publishing/main.py"],
    }
    assert set(readers) == set(MATRIX), (
        "every matrix var needs a named reader (and vice versa)")

    def is_read(var: str, text: str) -> bool:
        import re

        if re.search(rf"""["']{re.escape(var)}["']""", text):
            return True
        # Urdu TTS settings are read through
        # ``os.environ.get(f"TTS_BASE_URL_{language.upper()}")``.
        for base in ("TTS_BASE_URL", "TTS_API_KEY", "TTS_MODEL", "TTS_VOICE"):
            if var == f"{base}_UR" and f"{base}_{{language.upper()}}" in text:
                return True
        # Publishing builds the Instagram names from a per-account prefix
        # (``f"{prefix}USER_ID"`` / ``f"{prefix}ACCESS_TOKEN"``).
        if var == "INSTAGRAM_USER_ID" and "{prefix}USER_ID" in text:
            return True
        if var == "INSTAGRAM_ACCESS_TOKEN" and "{prefix}ACCESS_TOKEN" in text:
            return True
        return False

    missing: list[str] = []
    for var, files in readers.items():
        for rel in files:
            if not is_read(var, (_REPO / rel).read_text()):
                missing.append(f"{var} in {rel}")
    assert not missing, (
        "these settings are no longer read by their named consumer: "
        + ", ".join(missing))
