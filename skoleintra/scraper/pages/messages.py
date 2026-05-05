"""Messages / dialogue scraper for ForældreIntra.

Inspired by fskintra's ``pgDialogue.py``.  Supports the modern
"conversations" view (``/messages/conversations``).

The portal embeds conversation metadata as JSON in a ``data-*``
attribute of a ``<div>`` in the page.  For each conversation whose
latest message has not been seen before we load the full thread and
convert every message into a :class:`ScrapedItem`.
"""

import html
import json
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from skoleintra.scraper.models import ScrapedAttachment, ScrapedItem
from skoleintra.scraper.session import PortalSession

logger = logging.getLogger(__name__)

ITEM_TYPE = "message"


def scrape(portal: PortalSession, child_url_prefix: str) -> list[ScrapedItem]:
    """Fetch and parse all messages for one child.

    Parameters
    ----------
    portal:
        Authenticated portal session.
    child_url_prefix:
        URL prefix for the child, e.g.
        ``https://school.foraldreintra.dk/parent/1234/ChildName``.

    Returns
    -------
    list[ScrapedItem]
        All messages found (may include already-seen ones; deduplication
        happens in the DB upsert layer).
    """
    url = f"{child_url_prefix}/messages/conversations"
    logger.info("Fetching messages from %s", url)
    resp = portal.get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    conversations = _extract_conversations(soup)
    if conversations is None:
        logger.warning("No conversations JSON found on %s", url)
        return []

    items: list[ScrapedItem] = []
    for conv in conversations:
        thread_id = str(conv.get("ThreadId") or "")
        latest_mid = str(conv.get("LatestMessageId") or "")
        if not latest_mid:
            logger.debug("Skipping conversation with no LatestMessageId: %r", conv)
            continue

        msgs = _load_thread(portal, child_url_prefix, thread_id, latest_mid)
        for raw_msg in msgs:
            item = _msg_to_scraped_item(raw_msg, thread_id)
            if item is not None:
                items.append(item)

    logger.info("Found %d message(s) for %s", len(items), child_url_prefix)
    return items


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_conversations(soup: BeautifulSoup) -> list[dict] | None:
    """Locate the JSON conversations blob embedded in the page."""
    main = soup.find("div", class_="sk-l-content-wrapper") or soup
    for div in main.find_all("div"):
        for attr_name, attr_val in div.attrs.items():
            if "message" not in attr_name.lower():
                continue
            if not isinstance(attr_val, str) or len(attr_val) < 50:
                continue
            try:
                data = json.loads(attr_val)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(data, dict):
                convs = data.get("Conversations")
                if isinstance(convs, list):
                    return convs
    return None


def _load_thread(
    portal: PortalSession,
    child_url_prefix: str,
    thread_id: str,
    latest_mid: str,
) -> list[dict]:
    """Load the full message list for a conversation thread."""
    if thread_id:
        suffix = (
            "/messages/conversations/loadmessagesforselectedconversation"
            f"?threadId={thread_id}"
            f"&takeFromRootMessageId={latest_mid}"
            "&takeToMessageId=0"
            "&searchRequest="
        )
    else:
        suffix = (
            "/messages/conversations/getmessageforthreadlessconversation"
            f"?messageId={latest_mid}"
        )

    url = f"{child_url_prefix}{suffix}"
    logger.debug("Loading thread from %s", url)
    try:
        resp = portal.get(url)
        data = json.loads(resp.text)
    except Exception as exc:
        logger.warning("Could not load thread %s/%s: %s", thread_id, latest_mid, exc)
        return []

    if thread_id:
        return data if isinstance(data, list) else []
    return [data] if isinstance(data, dict) else []


def _msg_to_scraped_item(msg: dict, thread_id: str) -> ScrapedItem | None:
    """Convert a raw message dict from the portal to a :class:`ScrapedItem`."""
    mid = str(msg.get("Id") or "")
    if not mid:
        logger.debug("Skipping message with no Id: %r", msg)
        return None

    external_id = f"{thread_id}--{mid}" if thread_id else mid

    subject = _normalize_text(msg.get("Subject") or "")
    sender = _normalize_text(msg.get("SenderName") or "")

    base_text = _normalize_text(msg.get("BaseText") or "")
    prev_text = _normalize_text(msg.get("PreviousMessagesText") or "")
    body_html = f'<div class="base">{base_text}</div>\n'
    if prev_text:
        body_html += f'<div class="prev">{prev_text}</div>\n'

    date = _parse_date(msg.get("SentReceivedDateText"))

    attachments: list[ScrapedAttachment] = []
    for att in msg.get("AttachmentsLinks") or []:
        href = att.get("HrefAttributeValue") or ""
        text = _normalize_text(att.get("Text") or href)
        if href:
            attachments.append(ScrapedAttachment(filename=text, url=href))

    return ScrapedItem(
        type=ITEM_TYPE,
        external_id=external_id,
        title=subject,
        sender=sender,
        body_html=body_html,
        date=date,
        raw_json=msg,
        attachments=attachments,
    )


# Patterns like "15. jan. 2024 13:45" or "15/01/2024 13:45"
_DATE_PATTERNS = [
    (
        re.compile(r"(\d{1,2})\.\s*(\w+\.?)\s*(\d{4})\s+(\d{2}):(\d{2})"),
        "da_long",
    ),
    (
        re.compile(r"(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2})"),
        "iso",
    ),
]

_DA_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "maj": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "okt": 10,
    "nov": 11,
    "dec": 12,
}


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip().replace("\xa0", " ")
    for pattern, fmt in _DATE_PATTERNS:
        m = pattern.search(raw)
        if not m:
            continue
        try:
            if fmt == "da_long":
                day, month_str, year, hour, minute = m.groups()
                month = _DA_MONTHS.get(month_str.rstrip(".").lower()[:3])
                if month is None:
                    continue
                return datetime(
                    int(year),
                    month,
                    int(day),
                    int(hour),
                    int(minute),
                    tzinfo=timezone.utc,
                )
            if fmt == "iso":
                dd, mm, year, hour, minute = m.groups()
                return datetime(
                    int(year),
                    int(mm),
                    int(dd),
                    int(hour),
                    int(minute),
                    tzinfo=timezone.utc,
                )
        except ValueError:
            continue
    logger.debug("Could not parse date %r", raw)
    return None


def _normalize_text(value: str) -> str:
    """Decode HTML entities and normalize non-breaking spaces for storage."""
    return html.unescape(value).replace("\xa0", " ")
