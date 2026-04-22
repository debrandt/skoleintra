"""Discover children registered on the portal.

After login the index page contains navigation links that identify
each child and their URL prefix.  This module extracts them.

Inspired by fskintra's ``schildren.py``.
"""

import logging
import re

from bs4 import BeautifulSoup

from skoleintra.scraper.session import PortalSession

logger = logging.getLogger(__name__)


def get_children(portal: PortalSession, index_soup: BeautifulSoup) -> dict[str, str]:
    """Return a mapping of child name → URL prefix from the index page.

    Parameters
    ----------
    portal:
        Authenticated portal session (used to make URLs absolute).
    index_soup:
        Parsed HTML of the post-login index page.

    Returns
    -------
    dict[str, str]
        e.g. ``{"Andrea 0A": "https://school.foraldreintra.dk/parent/1234/Andrea"}``
    """
    children: dict[str, str] = {}
    seen_urls: set[str] = set()

    # The personal menu button label is the name of the "first" child
    first_child_name = ""
    btn = index_soup.find(id="sk-personal-menu-button")
    if btn:
        first_child_name = btn.get_text(strip=True)

    # Navigation links for each child follow the pattern:
    # /parent/<id>/<name>/Index
    for a in index_soup.find_all("a", href=re.compile(r"^(/[^/]+){3}/Index$")):
        href: str = a["href"]
        url_prefix = href.rsplit("/", 1)[0].rstrip("/")
        abs_prefix = portal.abs_url(url_prefix)
        if abs_prefix in seen_urls:
            continue
        seen_urls.add(abs_prefix)

        name = a.get_text(strip=True) or first_child_name
        if name and name not in children:
            logger.debug("Found child %r → %s", name, abs_prefix)
            children[name] = abs_prefix

    if not children:
        logger.warning(
            "No children found on the index page. "
            "The portal structure may have changed."
        )
    else:
        logger.info("Children found: %s", ", ".join(sorted(children)))

    return children
