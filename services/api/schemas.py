"""API request/response schemas (Pydantic v2)."""

import base64
import binascii
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Final, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from document_sections import MAX_DOCUMENT_CHARS

# G06: the adapter-kind registry in `packages/` is authoritative for the API
# too, so a new adapter cannot exist in the collector while `SourceIn` still
# refuses to create it.
_PACKAGES = Path(__file__).resolve().parents[2] / "packages"
if str(_PACKAGES) not in sys.path:
    sys.path.insert(0, str(_PACKAGES))

from source_adapters.registry import missing_config as _adapter_missing_config  # noqa: E402
from source_adapters.registry import approval_denial as _adapter_approval_denial  # noqa: E402
from source_adapters.registry import ADAPTER_KINDS as _ADAPTER_KINDS  # noqa: E402

TrustTier = Literal["A_provider_owned", "B_discovery_lead", "C_excluded"]
# Keep this Literal in sync with registry.ADAPTER_KINDS — the guard test
# `test_registry_sync` fails the suite if the two drift apart.
AdapterKind = Literal[
    "rss", "github_releases", "page_watch", "hf_papers", "hn_search",
    "github_stars", "reddit_new", "google_trends_rss", "extension", "manual",
]
assert set(_ADAPTER_KINDS) == set(AdapterKind.__args__)  # import-time sync check
OfferStateL = Literal[
    "candidate",
    "evidence_needed",
    "verified",
    "approved_for_video",
    "published",
    "expired",
    "corrected",
]


# ---------------------------------------------------------------- items


class ItemIn(BaseModel):
    """A candidate observed by a collector or saved via the browser extension."""

    source_id: Optional[uuid.UUID] = None  # collectors pass this; extension omitted
    external_item_id: Optional[str] = None  # stable id from the source
    url: HttpUrl
    title: Optional[str] = None
    selection: Optional[str] = None  # text selected in the browser, if any
    account_handle: Optional[str] = None
    text: Optional[str] = None  # body/excerpt for hashing (collectors)
    published_at: Optional[datetime] = None
    observed_at: Optional[datetime] = None


class ItemOut(BaseModel):
    id: uuid.UUID
    url: str
    canonical_url: Optional[str]
    title: Optional[str]
    observed_at: datetime
    published_at: Optional[datetime]
    duplicate_group: Optional[str]
    processed: bool
    source_provider: Optional[str]
    source_category: Optional[str]
    trust_tier: Optional[str]


# ---------------------------------------------------------------- sources


class SourceIn(BaseModel):
    provider: str = Field(min_length=2)
    canonical_domain: Optional[str] = None
    account_handle: Optional[str] = None
    category: str
    adapter: AdapterKind
    config: dict[str, Any] = Field(default_factory=dict)
    polling_cadence: str = "6 hours"
    country_scope: list[str] = Field(default_factory=list)
    trust_tier: TrustTier = "B_discovery_lead"
    enabled: bool = True

    @model_validator(mode="after")
    def _adapter_config_present(self):
        """G06: a source must be registrable AND runnable — reject kinds whose
        required adapter config is missing at creation time (with the seed
        script now going through the same rules) instead of letting the
        collector discover the hole on its first poll."""
        absent = _adapter_missing_config(self.adapter, self.config)
        if absent:
            raise ValueError(
                f"adapter {self.adapter!r} requires config key(s): {', '.join(absent)}")
        # G22 [S10]: approval-pending adapters (currently Reddit) are off by
        # default — public visibility or robots compliance is not a license.
        # Only an explicit operator lift (registry `lift_env`) may create an
        # ENABLED source; recording it disabled ahead of approval stays allowed.
        if self.enabled:
            denial = _adapter_approval_denial(self.adapter)
            if denial:
                raise ValueError(denial)
        return self


class PollResult(BaseModel):
    created: int = 0
    ok: bool = True
    detail: Optional[str] = None


class TosReviewIn(BaseModel):
    """A human attestation that automated reading of a source is permitted.

    `reference` points at the terms/contract the reviewer read (a URL, ticket or
    document id) so the decision is auditable later; free text with no reference
    is not an attestation.
    """

    model_config = ConfigDict(extra="forbid")

    reference: str = Field(strict=True, min_length=3, max_length=500, pattern=r"\S")
    reviewer: Optional[str] = Field(default=None, min_length=1, max_length=200, pattern=r"\S")


# ---------------------------------------------------------------- offers


class OfferIn(BaseModel):
    """Create an offer (from a promoted item or directly by a reviewer)."""

    title: Optional[str] = None  # defaults to the promoted item's title
    provider: str = Field(min_length=2)
    category: str
    offer_type: str
    promo_code: Optional[str] = None
    redemption_url: Optional[HttpUrl] = None
    expires_at: Optional[datetime] = None
    eligibility: dict[str, Any] = Field(default_factory=dict)
    value: dict[str, Any] = Field(default_factory=dict)
    claim_steps: list[dict[str, Any]] = Field(default_factory=list)


class OfferUpdate(BaseModel):
    """Reviewer edit. Material changes demote the offer back to
    evidence_needed (re-verification) per the correction workflow (§3)."""

    title: Optional[str] = None
    provider: Optional[str] = None
    category: Optional[str] = None
    offer_type: Optional[str] = None
    eligibility: Optional[dict[str, Any]] = None
    value: Optional[dict[str, Any]] = None
    claim_steps: Optional[list[dict[str, Any]]] = None
    promo_code: Optional[str] = None
    redemption_url: Optional[HttpUrl] = None
    expires_at: Optional[datetime] = None
    renewal: Optional[dict[str, Any]] = None
    correction_note: Optional[str] = None


class TransitionIn(BaseModel):
    to: OfferStateL
    reviewer: Optional[str] = None  # required for approval targets
    note: Optional[str] = None


class RobotsPermission(BaseModel):
    """The provider's published robots policy at the moment of the fetch.

    ``allowed`` is only meaningful together with a readable file: a 401/403,
    429 or 5xx robots response means the policy is unknown or withheld, and the
    worker never proceeds. The API re-checks the shape so a caller cannot
    attest permission it never obtained.
    """

    robots_url: HttpUrl
    checked_at: datetime
    allowed: bool
    status: Optional[int] = Field(default=None, ge=100, le=599)

    @model_validator(mode="after")
    def _allowed_needs_a_readable_policy(self) -> "RobotsPermission":
        if self.allowed and (
            self.status is None
            or self.status in (401, 403, 429)
            or self.status >= 500
        ):
            raise ValueError(
                "an allowed robots decision requires a readable robots.txt "
                "(not an auth wall, rate limit or server error)"
            )
        return self


class EvidenceProvenance(BaseModel):
    """How the raw bytes were obtained (master plan §6 step 2).

    The API re-checks every URL against the provider allowlist and re-hashes the
    bytes; nothing here is trusted on the caller's word.
    """

    requested_url: HttpUrl
    final_url: HttpUrl
    http_status: int = Field(ge=100, le=599)
    content_type: str = Field(default="", max_length=200)
    fetched_at: datetime
    redirects: list[HttpUrl] = Field(default_factory=list, max_length=10)
    raw_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parser_version: str = Field(min_length=1, max_length=80)
    fetch_identity: Optional[str] = Field(default=None, max_length=120)
    encoding: Optional[str] = Field(default=None, max_length=40)
    robots: Optional[RobotsPermission] = None
    #: HMAC-SHA256 over the canonical provenance, produced by the acquisition
    #: worker with the deployment key. Shape only here; the API verifies it.
    signature: Optional[str] = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class EvidenceIn(BaseModel):
    """Immutable evidence snapshot. `captured_content` is hashed server-side;
    identical snapshots dedupe (never stored twice for the same offer).

    Verification also sends `raw_content_b64` (the exact bytes the provider
    served) and `provenance` (how they were fetched). The server decodes,
    re-hashes and validates both; a mismatch is a 422, never a silent accept.
    """

    url: HttpUrl
    source_id: Optional[uuid.UUID] = None
    excerpt: Optional[str] = None  # supporting quote
    captured_content: Optional[str] = Field(default=None, max_length=MAX_DOCUMENT_CHARS)
    raw_content_b64: Optional[str] = Field(default=None, max_length=2_800_000)
    provenance: Optional[EvidenceProvenance] = None
    screenshot_path: Optional[str] = None
    supported_fields: list[str] = Field(default_factory=list)
    official: bool = False  # Tier-A / provider-owned claim (verified requires it)
    reviewer: Optional[str] = None

    @field_validator("captured_content")
    @classmethod
    def bounded_snapshot(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and (not value.strip() or "\x00" in value):
            raise ValueError("snapshot must be nonblank text without NUL characters")
        return value

    @field_validator("raw_content_b64")
    @classmethod
    def decodable_raw_snapshot(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        try:
            raw = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("raw_content_b64 must be valid base64") from None
        if not raw:
            raise ValueError("raw snapshot must not be empty")
        if len(raw) > 2_000_000:
            raise ValueError("raw snapshot exceeds the 2,000,000-byte egress limit")
        return value

    @model_validator(mode="after")
    def provenance_pairing(self) -> "EvidenceIn":
        if self.provenance is not None and self.raw_content_b64 is None:
            raise ValueError("provenance requires raw_content_b64")
        return self


ExtractionFieldName = Literal[
    "promo_code", "price", "value", "benefit_type", "eligibility",
    "regions", "expiry", "renewal", "auto_renew",
]

#: Typed values for the claims whose meaning is not free text.
BENEFIT_TYPES: Final = ("free", "discounted", "application_based")
AUTO_RENEW_VALUES: Final = ("yes", "no")
#: A price must declare whether it is the initial price or the renewal price
#: so a renewal figure is never presented as the price a viewer pays first.
PRICE_BASES: Final = ("initial", "renewal")


class ExtractedField(BaseModel):
    """A literal claim bound to one immutable snapshot, not just a URL."""

    model_config = ConfigDict(extra="forbid")

    value: str = Field(strict=True, min_length=1, max_length=2000, pattern=r"\S")
    evidence_id: uuid.UUID
    evidence_url: HttpUrl
    excerpt: str = Field(strict=True, min_length=1, max_length=4000, pattern=r"\S")
    confidence: Optional[float] = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    #: "initial" or "renewal" — only meaningful for a price claim.
    basis: Optional[str] = Field(default=None, max_length=20)
    #: Regions the official terms explicitly exclude — only for a regions claim.
    excluded_regions: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("value", "excerpt")
    @classmethod
    def no_nul(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("claim text must not contain NUL characters")
        return value

    @field_validator("evidence_url")
    @classmethod
    def safe_evidence_url(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https" or value.username or value.password or value.fragment:
            raise ValueError("evidence must use a credential-free HTTPS URL without fragment")
        return value

    @field_validator("excluded_regions")
    @classmethod
    def clean_regions(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item or len(item) > 100 for item in cleaned):
            raise ValueError("excluded regions must be nonblank country/region names")
        return cleaned

    @model_validator(mode="after")
    def typed_claims(self) -> "ExtractedField":
        """Reject values that do not fit their claim type.

        These are hard errors rather than a later "unknown": a caller that
        claims `benefit_type=free` must actually mean one of the three
        benefit types, not an arbitrary string.
        """
        if self.basis is not None and self.basis not in PRICE_BASES:
            raise ValueError(f"basis must be one of {PRICE_BASES}")
        return self


class ExtractionCoverage(BaseModel):
    """What the extractor actually examined (WP01 slice 8).

    The API recomputes `sections_total` from the stored snapshot text, so a
    truncated read cannot claim full coverage. `evidence_ids` must all belong to
    the offer being extracted.
    """

    model_config = ConfigDict(extra="forbid")

    version: str = Field(strict=True, min_length=1, max_length=40,
                         pattern=r"^[a-z0-9-]+/\d+$")
    sections_total: int = Field(strict=True, ge=0, le=100_000)
    max_section_chars: int = Field(strict=True, ge=100, le=100_000)
    evidence_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class ExtractionIn(BaseModel):
    """Extractor proposal. `complete` is a compatibility hint, never authority."""

    model_config = ConfigDict(extra="forbid")

    fields: dict[ExtractionFieldName, ExtractedField] = Field(default_factory=dict, max_length=12)
    complete: bool = Field(default=False, strict=True)
    conflicts: list[dict[str, Any]] = Field(default_factory=list, max_length=64)
    model: Optional[str] = Field(default=None, max_length=200)
    #: WP-G (§5.6.3): honest attribution of HOW this proposal was produced —
    #: `llm`, `rules` (deterministic only) or `rules_fallback` (the LLM was
    #: attempted but produced nothing usable). Optional for legacy callers.
    method: Optional[str] = Field(default=None, max_length=40)
    #: Optional for legacy/manual callers; the acquisition worker always sends it.
    coverage: Optional[ExtractionCoverage] = None
    #: Human explanation when a reviewer edits claims or clears conflicts.
    review_note: Optional[str] = Field(default=None, min_length=3, max_length=2000)

    _ALLOWED_METHODS = {"llm", "rules", "rules_fallback"}

    @model_validator(mode="after")
    def known_method(self) -> "ExtractionIn":
        if self.method is not None and self.method not in self._ALLOWED_METHODS:
            raise ValueError(
                f"method must be one of {sorted(self._ALLOWED_METHODS)}")
        return self

    @model_validator(mode="after")
    def typed_claim_values(self) -> "ExtractionIn":
        """Each claim name accepts only the values that name can carry."""
        benefit = self.fields.get("benefit_type")
        if benefit is not None and benefit.value.strip().lower() not in BENEFIT_TYPES:
            raise ValueError(f"benefit_type value must be one of {BENEFIT_TYPES}")
        auto_renew = self.fields.get("auto_renew")
        if auto_renew is not None and auto_renew.value.strip().lower() not in AUTO_RENEW_VALUES:
            raise ValueError(f"auto_renew value must be one of {AUTO_RENEW_VALUES}")
        for name, field in self.fields.items():
            if name == "regions" and field.excluded_regions and not field.value.strip():
                raise ValueError("a regions claim with exclusions must name the eligible regions")
            if name != "regions" and field.excluded_regions:
                raise ValueError("excluded_regions is only valid for a regions claim")
            if name != "price" and field.basis:
                raise ValueError("basis is only valid for a price claim")
        return self


class ConflictResolutionIn(BaseModel):
    """One operator decision for one open extraction conflict.

    `value is None` means "keep the current claim as-is and dismiss the
    conflict"; a nonblank `value` replaces the claim and must cite evidence —
    either the cited snapshot on the existing field or an explicit
    `evidence_id` belonging to the same offer.
    """

    model_config = ConfigDict(extra="forbid")

    field: ExtractionFieldName
    value: Optional[str] = Field(default=None, max_length=2000)
    excerpt: Optional[str] = Field(default=None, max_length=4000)
    confidence: Optional[float] = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    evidence_id: Optional[uuid.UUID] = None
    #: Why this side of the disagreement is the correct one.
    note: Optional[str] = Field(default=None, max_length=2000)


class ConflictResolveIn(BaseModel):
    """Per-conflict triage: resolve some or all open conflicts in one pass.

    Conflicts not referenced here stay open. Clearing the last conflict always
    requires a human `review_note` (same contract as a fresh extraction).
    """

    model_config = ConfigDict(extra="forbid")

    resolutions: list[ConflictResolutionIn] = Field(min_length=1, max_length=64)
    review_note: str = Field(min_length=3, max_length=2000)
