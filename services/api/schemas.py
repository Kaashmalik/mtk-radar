"""API request/response schemas (Pydantic v2)."""

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl

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
    captured_content: Optional[str] = None  # raw fetched content to hash
    screenshot_path: Optional[str] = None
    supported_fields: list[str] = Field(default_factory=list)
    official: bool = False  # Tier-A / provider-owned claim (verified requires it)
    reviewer: Optional[str] = None


class ExtractionIn(BaseModel):
    """Structured extraction result; each field maps to its evidence URL."""

    fields: dict[str, dict[str, Any]] = Field(default_factory=dict)
    complete: bool = False
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    model: Optional[str] = None
