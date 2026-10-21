"""API request/response schemas (Pydantic v2)."""

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

TrustTier = Literal["A_provider_owned", "B_discovery_lead", "C_excluded"]
AdapterKind = Literal["rss", "github_releases", "page_watch", "extension", "manual"]
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


class PollResult(BaseModel):
    created: int = 0
    ok: bool = True
    detail: Optional[str] = None


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


class EvidenceIn(BaseModel):
    """Immutable evidence snapshot. `captured_content` is hashed server-side;
    identical snapshots dedupe (never stored twice for the same offer)."""

    url: HttpUrl
    source_id: Optional[uuid.UUID] = None
    excerpt: Optional[str] = None  # supporting quote
    captured_content: Optional[str] = Field(default=None, max_length=250_000)
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


ExtractionFieldName = Literal["promo_code", "price", "expiry", "eligibility", "renewal", "value"]


class ExtractedField(BaseModel):
    """A literal claim bound to one immutable snapshot, not just a URL."""

    model_config = ConfigDict(extra="forbid")

    value: str = Field(strict=True, min_length=1, max_length=2000, pattern=r"\S")
    evidence_id: uuid.UUID
    evidence_url: HttpUrl
    excerpt: str = Field(strict=True, min_length=1, max_length=4000, pattern=r"\S")
    confidence: Optional[float] = Field(default=None, ge=0, le=1, allow_inf_nan=False)

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


class ExtractionIn(BaseModel):
    """Extractor proposal. `complete` is a compatibility hint, never authority."""

    model_config = ConfigDict(extra="forbid")

    fields: dict[ExtractionFieldName, ExtractedField] = Field(default_factory=dict, max_length=6)
    complete: bool = Field(default=False, strict=True)
    conflicts: list[dict[str, Any]] = Field(default_factory=list, max_length=64)
    model: Optional[str] = Field(default=None, max_length=200)
