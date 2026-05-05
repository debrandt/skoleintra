"""Internal DTOs (data transfer objects) for scraped content.

These dataclasses are used to pass scraped data from page parsers
to the DB upsert layer without coupling those layers to each other.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ScrapedAttachment:
    """Normalised representation of one scraped attachment link."""

    filename: str
    url: str


@dataclass
class ScrapedItem:
    """Normalised representation of a single scraped portal item."""

    type: str
    """Identifies the section, e.g. ``'message'``, ``'frontpage'``."""

    external_id: str
    """Stable identifier from the portal (message ID, thread ID, …)."""

    title: str
    sender: str
    body_html: str
    date: datetime | None

    raw_json: dict | None = None
    """Raw JSON payload from the portal, stored for debugging."""

    attachments: list[ScrapedAttachment] = field(default_factory=list)
