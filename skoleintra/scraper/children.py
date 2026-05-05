"""Discover children registered on the portal.

After login the index page contains navigation links that identify
each child and their URL prefix.  This module extracts them.

Inspired by fskintra's ``schildren.py``.
"""

import logging
import re

from bs4 import BeautifulSoup

from skoleintra.db.identity import ChildSnapshot
from skoleintra.scraper.session import PortalSession

logger = logging.getLogger(__name__)
_CHILD_HREF_RE = re.compile(r"^(/[^/]+){3}/Index$")
_CHILD_SOURCE_ID_RE = re.compile(r"/parent/([^/]+)/")


def get_child_snapshots(
    portal: PortalSession, index_soup: BeautifulSoup
) -> list[ChildSnapshot]:
    """Return the visible children with canonical source IDs and URL prefixes.

    Parameters
    ----------
    portal:
        Authenticated portal session (used to make URLs absolute).
    index_soup:
        Parsed HTML of the post-login index page.

    Returns
    -------
    list[ChildSnapshot]
        e.g. ``[ChildSnapshot(source_id="1234", display_name="Andrea 0A", ...)]``
    """
    children: list[ChildSnapshot] = []
    seen_urls: set[str] = set()

    # The personal menu button label is the name of the "first" child
    first_child_name = ""
    btn = index_soup.find(id="sk-personal-menu-button")
    if btn:
        first_child_name = btn.get_text(strip=True)

    # Navigation links for each child follow the pattern:
    # /parent/<id>/<name>/Index
    for a in index_soup.find_all("a", href=_CHILD_HREF_RE):
        href: str = a["href"]
        url_prefix = href.rsplit("/", 1)[0].rstrip("/")
        abs_prefix = portal.abs_url(url_prefix)
        if abs_prefix in seen_urls:
            continue
        seen_urls.add(abs_prefix)

        name = a.get_text(strip=True) or first_child_name
        source_id = _extract_child_source_id(abs_prefix)
        if name and source_id:
            logger.debug("Found child %r (%s) → %s", name, source_id, abs_prefix)
            children.append(
                ChildSnapshot(
                    source_id=source_id,
                    display_name=name,
                    url_prefix=abs_prefix,
                )
            )

    if not children:
        logger.warning(
            "No children found on the index page. "
            "The portal structure may have changed."
        )
    else:
        logger.info(
            "Children found: %s",
            ", ".join(sorted(child.display_name for child in children)),
        )

    return children


def get_children(portal: PortalSession, index_soup: BeautifulSoup) -> dict[str, str]:
    """Return a legacy mapping of child name → URL prefix from the index page."""
    return {
        child.display_name: child.url_prefix or ""
        for child in get_child_snapshots(portal, index_soup)
    }


def _extract_child_source_id(url_prefix: str) -> str | None:
    match = _CHILD_SOURCE_ID_RE.search(url_prefix)
    if match:
        return match.group(1)
    return None
