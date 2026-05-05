from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from skoleintra.blobs.client import guess_content_type, upload_blob
from skoleintra.db.models import Attachment
from skoleintra.settings import Settings

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
    s3_client,
    settings: Settings,
    item_date: datetime | None,
    not_older_than: datetime | None = None,
    debug: bool = False,
) -> PhotoSyncResult:
    result = PhotoSyncResult()
    _ = db_session

    if s3_client is None or not settings.blob_s3_bucket:
        return result

    if attachment.blob_key:
        return result

    if not_older_than is not None and item_date is not None:
        if item_date < not_older_than:
            result.skipped_old += 1
            return result

    response = portal.get(attachment.url)
    payload = response.content
    content_type = (
        response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        or guess_content_type(attachment.filename)
    )
    if not _is_photo_attachment(attachment.filename, attachment.url, content_type):
        result.skipped_non_photo += 1
        return result

    if debug:
        print(
            "photos: uploading "
            f"attachment_id={attachment.id} size={len(payload)} "
            f"content_type={content_type or 'unknown'}"
        )

    item = attachment.item
    prefix = settings.blob_s3_prefix.strip("/")
    key = f"{prefix}/{item.child_id}/{item.type}/{item.id}/{attachment.filename}"
    upload_blob(s3_client, settings.blob_s3_bucket, key, payload, content_type)
    attachment.blob_key = key
    attachment.content_type = content_type
    attachment.size_bytes = len(payload)
    result.downloaded += 1
    return result


def prune_photo_blobs(db_session: Session, retention_days: int | None) -> int:
    _ = db_session
    _ = retention_days
    return 0


def _is_photo_attachment(filename: str, url: str, content_type: str | None) -> bool:
    if content_type and content_type.startswith("image/"):
        return True

    candidate = (filename or "") + " " + (url or "")
    lowered = candidate.lower()
    return any(ext in lowered for ext in _IMAGE_EXTENSIONS)
