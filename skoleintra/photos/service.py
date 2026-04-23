from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from skoleintra.db.models import Attachment, AttachmentBlob
from skoleintra.db.upsert import upsert_attachment_blob

if TYPE_CHECKING:
    from skoleintra.scraper.session import PortalSession

_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".heic",
    ".heif",
    ".bmp",
    ".tiff",
    ".avif",
}


@dataclass(slots=True)
class PhotoSyncResult:
    downloaded: int = 0
    skipped_old: int = 0
    skipped_non_photo: int = 0


def parse_not_older_than_date(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.strptime(value, "%Y-%m-%d").date()
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)


def sync_attachment_blob(
    db_session: Session,
    portal: PortalSession,
    attachment: Attachment,
    *,
    item_date: datetime | None,
    not_older_than: datetime | None = None,
    debug: bool = False,
) -> PhotoSyncResult:
    result = PhotoSyncResult()

    if _has_blob(db_session, attachment.id):
        return result

    if not_older_than is not None and item_date is not None:
        if item_date < not_older_than:
            result.skipped_old += 1
            return result

    response = portal.get(attachment.url)
    payload = response.content
    content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower() or None
    if not _is_photo_attachment(attachment.filename, attachment.url, content_type):
        result.skipped_non_photo += 1
        return result

    if debug:
        print(
            "photos: storing "
            f"attachment_id={attachment.id} size={len(payload)} "
            f"content_type={content_type or 'unknown'}"
        )

    upsert_attachment_blob(
        db_session,
        attachment,
        blob=payload,
        sha256=hashlib.sha256(payload).hexdigest(),
        content_type=content_type,
    )
    result.downloaded += 1
    return result


def prune_photo_blobs(db_session: Session, retention_days: int | None) -> int:
    if retention_days is None:
        return 0
    if retention_days < 0:
        raise ValueError("retention_days must be >= 0")

    keep_after = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted = db_session.execute(
        delete(AttachmentBlob).where(AttachmentBlob.downloaded_at < keep_after)
    )
    return deleted.rowcount or 0


def _has_blob(db_session: Session, attachment_id: int) -> bool:
    existing = db_session.execute(
        select(AttachmentBlob.id).where(AttachmentBlob.attachment_id == attachment_id)
    ).fetchone()
    return existing is not None


def _is_photo_attachment(filename: str, url: str, content_type: str | None) -> bool:
    if content_type and content_type.startswith("image/"):
        return True

    candidate = (filename or "") + " " + (url or "")
    lowered = candidate.lower()
    return any(ext in lowered for ext in _IMAGE_EXTENSIONS)
