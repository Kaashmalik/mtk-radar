"""API request/response schemas (Pydantic v2)."""

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl

TrustTier = Literal["A_provider_owned", "B_discovery_lead", "C_excluded"]
AdapterKind = Literal["rss", "github_releases", "page_watch", "extension", "manual"]


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
