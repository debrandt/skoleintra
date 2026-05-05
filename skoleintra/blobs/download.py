"""Download pending attachment blobs and upload them to S3."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from skoleintra.blobs.client import guess_content_type, upload_blob
from skoleintra.db.models import Attachment, Item
from skoleintra.scraper.session import PortalSession
from skoleintra.settings import Settings

logger = logging.getLogger(__name__)


def download_pending_attachments(
    portal: PortalSession,
    s3_client,
    settings: Settings,
    db_session: Session,
) -> int:
    """Download all attachments with no blob_key and upload them to S3.

    Uses the authenticated portal session so that protected URLs are accessible.
    Failures are logged as warnings and do not abort remaining downloads.

    Returns the count of successfully uploaded blobs.
    """
    if s3_client is None:
        return 0

    pending = (
        db_session.execute(
            select(Attachment)
            .options(joinedload(Attachment.item))
            .where(Attachment.item.has(Item.type != "photo"))
            .where(Attachment.blob_key.is_(None))
        )
        .scalars()
        .all()
    )

    if not pending:
        return 0

    prefix = settings.blob_s3_prefix.strip("/")
    bucket = settings.blob_s3_bucket
    uploaded = 0

    for att in pending:
        try:
            resp = portal.get(att.url)
            data = resp.content
            content_type = resp.headers.get("Content-Type", "").split(";")[
                0
            ].strip() or guess_content_type(att.filename)
            item = att.item
            key = f"{prefix}/{item.child_id}/{item.type}/{item.id}/{att.filename}"
            upload_blob(s3_client, bucket, key, data, content_type)
            att.blob_key = key
            att.content_type = content_type
            att.size_bytes = len(data)
            uploaded += 1
            logger.info("Uploaded blob: %s (%d bytes)", key, len(data))
        except Exception as exc:
            logger.warning(
                "Failed to download attachment id=%d url=%s: %s",
                att.id,
                att.url,
                exc,
            )

    return uploaded
