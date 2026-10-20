from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class RawItem:
    """One observed candidate, pre-dedup. The API performs final dedup."""

    external_item_id: str  # stable id from the source (entry id, release id, page hash)
    url: str
    title: Optional[str] = None
    published_at: Optional[datetime] = None
    text: str = ""  # short body/excerpt used for the text hash
    extra: dict = field(default_factory=dict)
