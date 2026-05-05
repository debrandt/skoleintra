"""Photos scraper for ForaeldreIntra.

The live portal exposes child-accessible photos under ``/photos/albums``.
The listing page contains album cards, and each album page contains the
actual image URLs under ``/file/photoalbum/<album-id>/...``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from skoleintra.scraper.models import ScrapedAttachment, ScrapedItem
from skoleintra.scraper.session import PortalSession

logger = logging.getLogger(__name__)

ALBUM_ITEM_TYPE = "photo_album"
ITEM_TYPE = "photo"


def scrape(
    portal: PortalSession,
    child_url_prefix: str,
    *,
    cache_ttl_seconds: int | None = None,
) -> list[ScrapedItem]:
    """Scrape photo albums for one child and return them as ``ScrapedItem`` rows."""
    url = f"{child_url_prefix}/photos/albums"
    logger.info("Fetching photo albums from %s", url)
    resp = portal.get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    album_links = soup.select("a.sk-photoalbums-list-item[href]")
    if not album_links:
        logger.debug("No photo albums found for %s", child_url_prefix)
        return []

    items: list[ScrapedItem] = []
    seen_urls: set[str] = set()
    for album_link in album_links:
        album_url = portal.abs_url((album_link.get("href") or "").strip())
        if not album_url or album_url in seen_urls:
            continue
        seen_urls.add(album_url)

        if not album_url.startswith(child_url_prefix):
            logger.debug("Skipping out-of-scope album URL: %s", album_url)
            continue

        album_name = _album_title(album_link)
        album_description = _album_description(album_link)
        album_author = _album_author(album_link)

        try:
            album_resp = portal.get(album_url, cache_ttl_seconds=cache_ttl_seconds)
        except Exception as exc:
            logger.warning("Failed to fetch photo album %s: %s", album_url, exc)
            continue

        album_soup = BeautifulSoup(album_resp.text, "lxml")
        image_urls = _extract_image_urls(album_soup, portal)
        if not image_urls:
            continue

        external_id = _album_external_id(album_url)
        date = _extract_date(album_name, album_soup)
        attachments = [
            ScrapedAttachment(filename=_filename_for(url), url=url)
            for url in image_urls
        ]

        body_parts = [f"<p>{album_name}</p>", f"<p>Photos: {len(image_urls)}</p>"]
        if album_description:
            body_parts.append(f"<p>{album_description}</p>")
        body_html = "\n".join(body_parts) + "\n"

        album_raw = {
            "album_url": album_url,
            "count": len(image_urls),
            "description": album_description,
            "author": album_author,
        }

        items.append(
            ScrapedItem(
                type=ALBUM_ITEM_TYPE,
                external_id=external_id,
                title=f"Photo album: {album_name}",
                sender=album_author or "SkoleIntra",
                body_html=body_html,
                date=date,
                raw_json=album_raw,
            )
        )
        items.extend(
            ScrapedItem(
                type=ITEM_TYPE,
                external_id=f"{external_id}:{attachment.url}",
                title=f"Photo: {album_name}",
                sender=album_author or "SkoleIntra",
                body_html=body_html,
                date=date,
                raw_json={**album_raw, "photo_url": attachment.url},
                attachments=[attachment],
            )
            for attachment in attachments
        )

    logger.info("Found %d photo album item(s) for %s", len(items), child_url_prefix)
    return items


def _extract_image_urls(soup: BeautifulSoup, portal: PortalSession) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    for gallery in soup.find_all(
        attrs={
            "data-clientlogic-settings-photoalbum": True,
        }
    ):
        payload = (
            gallery.get("data-clientlogic-settings-photoalbum")
            or gallery.get("data-clientlogic-settings-PhotoAlbum")
            or ""
        ).strip()
        if not payload:
            continue

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue

        items = parsed.get("GalleryModel", {}).get("Items", [])
        if not isinstance(items, list):
            continue

        for entry in items:
            if not isinstance(entry, dict):
                continue
            src = str(entry.get("Source") or "").strip()
            if not src:
                continue
            abs_url = portal.abs_url(src)
            if "/file/photoalbum/" not in abs_url or abs_url in seen:
                continue
            seen.add(abs_url)
            urls.append(abs_url)

    for img in soup.select("img"):
        src = (img.get("src") or "").strip()
        if not src or src.startswith("data:"):
            continue
        abs_url = portal.abs_url(src)
        if "/file/photoalbum/" not in abs_url:
            continue
        if abs_url in seen:
            continue
        seen.add(abs_url)
        urls.append(abs_url)
    return urls


def _album_title(album_link: BeautifulSoup) -> str:
    title = album_link.select_one(".sk-photoalbum-list-item-title")
    return title.get_text(" ", strip=True) if title else "Photo album"


def _album_description(album_link: BeautifulSoup) -> str:
    description = album_link.select_one(".sk-photoalbum-list-item-description")
    return description.get_text(" ", strip=True) if description else ""


def _album_author(album_link: BeautifulSoup) -> str:
    author = album_link.select_one(".sk-photoalbum-list-item-author")
    if not author:
        return ""
    text = author.get_text(" ", strip=True)
    prefix = "Oprettet af:"
    return text[len(prefix) :].strip() if text.startswith(prefix) else text


def _album_external_id(url: str) -> str:
    match = re.search(r"/photos/albums/album/photos/(\d+)", url)
    if match:
        return match.group(1)
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def _filename_for(url: str) -> str:
    name = url.rsplit("/", 1)[-1].split("?", 1)[0].strip()
    return name or "photo"


def _extract_date(folder_name: str, soup: BeautifulSoup) -> datetime | None:
    candidates = [folder_name, soup.get_text(" ", strip=True)]

    # dd.mm.yyyy or dd/mm/yyyy
    for text in candidates:
        m = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", text)
        if m:
            dd, mm, yyyy = m.groups()
            try:
                return datetime(int(yyyy), int(mm), int(dd), tzinfo=timezone.utc)
            except ValueError:
                pass

    # yyyy-mm-dd
    for text in candidates:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if m:
            yyyy, mm, dd = m.groups()
            try:
                return datetime(int(yyyy), int(mm), int(dd), tzinfo=timezone.utc)
            except ValueError:
                pass

    return None
