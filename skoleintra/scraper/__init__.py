"""Scraper orchestration.

``run_scrape()`` is the single entry-point called by the CLI ``scrape``
command.  It:

1. Builds a :class:`~skoleintra.scraper.session.PortalSession`.
2. Logs in to the portal.
3. Discovers children.
4. For each child, runs all enabled page scrapers.
5. Upserts results into the database.
6. Prints a run summary.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

from skoleintra.blobs.client import get_s3_client
from skoleintra.blobs.download import download_pending_attachments
from skoleintra.db import session_scope
from skoleintra.db.upsert import upsert_attachment, upsert_child, upsert_item
from skoleintra.photos import prune_photo_blobs, sync_attachment_blob
from skoleintra.scraper.children import get_children
from skoleintra.scraper.login import login
from skoleintra.scraper.pages import messages as messages_scraper
from skoleintra.scraper.pages import photos as photos_scraper
from skoleintra.scraper.session import PortalSession
from skoleintra.settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class ScrapeResult:
    children_found: int = 0
    items_new: int = 0
    items_updated: int = 0
    attachments: int = 0
    blobs_uploaded: int = 0
    photo_blobs_downloaded: int = 0
    photo_blobs_pruned: int = 0
    photo_blobs_skipped_old: int = 0
    photo_blobs_skipped_non_photo: int = 0
    errors: list[str] = field(default_factory=list)


def run_scrape(
    settings: Settings,
    debug: bool = False,
    photo_not_older_than: datetime | None = None,
    photo_retention_days: int | None = None,
) -> ScrapeResult:
    """Run a full scrape cycle.

    Parameters
    ----------
    settings:
        Populated :class:`~skoleintra.settings.Settings` instance.
    debug:
        When *True*, save the failure HTML to ``state_dir`` on errors.

    Returns
    -------
    ScrapeResult
        Summary counts for the run.
    """
    result = ScrapeResult()

    portal = PortalSession(
        hostname=settings.hostname,
        state_dir=settings.state_dir,
    )

    s3_client = get_s3_client(settings)

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    logger.info("Logging in to %s (login_type=%s)", settings.hostname, settings.login_type)
    try:
        index_soup = login(
            portal,
            username=settings.username,
            password=settings.password,
            login_type=settings.login_type,
        )
    except Exception as exc:
        msg = f"Login failed: {exc}"
        logger.error(msg)
        result.errors.append(msg)
        return result

    # ------------------------------------------------------------------
    # Discover children
    # ------------------------------------------------------------------
    children = get_children(portal, index_soup)
    result.children_found = len(children)
    if not children:
        result.errors.append("No children found on the index page")
        return result

    # ------------------------------------------------------------------
    # Scrape each child
    # ------------------------------------------------------------------
    with session_scope() as db_session:
        result.photo_blobs_pruned = prune_photo_blobs(db_session, photo_retention_days)

        for child_name, child_url_prefix in sorted(children.items()):
            logger.info("Processing child: %s", child_name)
            child_obj = upsert_child(db_session, child_name, settings.hostname)

            # Messages
            try:
                scraped_items = messages_scraper.scrape(portal, child_url_prefix)
            except Exception as exc:
                msg = f"[{child_name}] messages scraper failed: {exc}"
                logger.error(msg)
                result.errors.append(msg)
                if debug:
                    portal.save_debug_artifact(
                        f"{child_name}_messages_error.html", str(exc)
                    )
                continue

            # Photos
            try:
                photo_items = photos_scraper.scrape(portal, child_url_prefix)
                scraped_items.extend(photo_items)
            except Exception as exc:
                msg = f"[{child_name}] photos scraper failed: {exc}"
                logger.error(msg)
                result.errors.append(msg)
                if debug:
                    portal.save_debug_artifact(
                        f"{child_name}_photos_error.html", str(exc)
                    )

            for scraped in scraped_items:
                try:
                    item_obj, is_new = upsert_item(db_session, child_obj, scraped)
                    if is_new:
                        result.items_new += 1
                        logger.info(
                            "[%s] New %s: %s", child_name, scraped.type, scraped.title
                        )
                    else:
                        result.items_updated += 1

                    for att in scraped.attachments:
                        db_att = upsert_attachment(db_session, item_obj, att.filename, att.url)
                        result.attachments += 1

                        if scraped.type == photos_scraper.ITEM_TYPE:
                            photo_sync_result = sync_attachment_blob(
                                db_session,
                                portal,
                                db_att,
                                s3_client=s3_client,
                                settings=settings,
                                item_date=scraped.date,
                                not_older_than=photo_not_older_than,
                                debug=debug,
                            )
                            result.photo_blobs_downloaded += photo_sync_result.downloaded
                            result.photo_blobs_skipped_old += photo_sync_result.skipped_old
                            result.photo_blobs_skipped_non_photo += (
                                photo_sync_result.skipped_non_photo
                            )
                except Exception as exc:
                    msg = f"[{child_name}] DB upsert failed for {scraped.external_id}: {exc}"
                    logger.error(msg)
                    result.errors.append(msg)

        result.blobs_uploaded += download_pending_attachments(
            portal, s3_client, settings, db_session
        )

    return result
