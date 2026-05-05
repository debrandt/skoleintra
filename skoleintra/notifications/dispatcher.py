"""Notification queue loading, formatting, and channel delivery helpers."""

from __future__ import annotations

import html
import logging
import re
import smtplib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Callable

import requests
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from skoleintra.blobs.client import (
    download_blob,
    generate_presigned_url,
    get_s3_client,
    guess_content_type,
)
from skoleintra.db.models import Item, NotificationSetting
from skoleintra.db.session import SessionLocal
from skoleintra.settings import Settings, get_settings

logger = logging.getLogger(__name__)

DEFAULT_NOTIFICATION_TYPES = (
    "message",
    "homework",
    "document",
    "photo",
    "weekplan",
)

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


@dataclass(slots=True)
class DispatchResult:
    """Aggregate counters for one notification dispatch run."""

    bootstrap_created: int = 0
    processed: int = 0
    sent: int = 0
    skipped: int = 0
    failed: int = 0


@dataclass(slots=True)
class EmailConfig:
    """SMTP configuration for parent-facing notifications."""

    host: str | None
    port: int
    username: str | None
    password: str | None
    sender: str | None
    recipients: list[str]
    use_ssl: bool
    starttls: bool

    @property
    def enabled(self) -> bool:
        """Whether the email channel has enough configuration to send items."""
        return bool(self.host and self.sender and self.recipients)


@dataclass(slots=True)
class NtfyConfig:
    """ntfy configuration for parent-facing notifications."""

    url: str | None
    default_topic: str | None
    token: str | None

    @property
    def enabled(self) -> bool:
        """Whether the ntfy channel has enough configuration to send items."""
        return bool(self.url and self.default_topic)


def dispatch_notifications(
    limit: int = 50, dry_run: bool = False, debug: bool = False
) -> DispatchResult:
    """Process pending items and send them through all enabled channels."""
    result = DispatchResult()
    app_settings = get_settings()

    with SessionLocal() as session:
        result.bootstrap_created = _bootstrap_notification_settings(session)

        pending = _load_pending_items(session, limit)
        if not pending:
            if dry_run:
                session.rollback()
            else:
                session.commit()
            return result

        email_cfg = _read_email_config(app_settings)
        ntfy_cfg = _read_ntfy_config(app_settings)
        s3_client = get_s3_client(app_settings)

        if not email_cfg.enabled and not ntfy_cfg.enabled:
            print("notify: no channels configured; set SMTP_*/NTFY_* values in .env")

        for item, settings in pending:
            result.processed += 1
            sent_at = _sent_at_for_item(item)

            if debug:
                print(
                    "notify: queue "
                    f"item_id={item.id} sent_at={sent_at.isoformat() if sent_at else 'unknown'} "
                    f"title={_clean_text(item.title, default='(untitled)')}"
                )

            email_enabled = bool(settings.email_enabled) if settings else True
            ntfy_enabled = bool(settings.ntfy_enabled) if settings else True
            ntfy_topic = (
                settings.ntfy_topic
                if settings and settings.ntfy_topic
                else ntfy_cfg.default_topic
            )
            state = _get_notify_state(item)

            wants_email = email_enabled and email_cfg.enabled
            wants_ntfy = ntfy_enabled and ntfy_cfg.enabled and bool(ntfy_topic)
            pending_email = wants_email and not state["email_sent"]
            pending_ntfy = wants_ntfy and not state["ntfy_sent"]
            active_channels = int(wants_email) + int(wants_ntfy)
            channels = []
            if pending_email:
                channels.append("email")
            if pending_ntfy:
                channels.append("ntfy")
            if not channels:
                channels.append("none")

            if dry_run:
                if channels == ["none"]:
                    result.skipped += 1
                else:
                    result.sent += 1
                print(
                    "notify[dry-run]: "
                    f"item_id={item.id} type={item.type!r} "
                    f"channels={','.join(channels)}"
                )
                continue

            if active_channels == 0:
                # Nothing is currently enabled/configured for this item.
                if debug:
                    print(
                        f"notify: skipping item_id={item.id} due to no active channels"
                    )
                result.skipped += 1
                continue

            sent_ok = True

            if pending_email:
                ok, err = _with_retries(
                    lambda item=item: _send_email(
                        item=item,
                        cfg=email_cfg,
                        s3_client=s3_client,
                        settings=app_settings,
                    ),
                    action=f"email item_id={item.id}",
                )
                if not ok:
                    sent_ok = False
                    print(f"notify: failed email for item_id={item.id}: {err}")
                else:
                    _set_notify_channel_sent(item, channel="email")

            if pending_ntfy and ntfy_topic:
                ok, err = _with_retries(
                    lambda item=item, ntfy_topic=ntfy_topic: _send_ntfy(
                        item=item,
                        cfg=ntfy_cfg,
                        topic=ntfy_topic,
                        s3_client=s3_client,
                        settings=app_settings,
                    ),
                    action=f"ntfy item_id={item.id}",
                )
                if not ok:
                    sent_ok = False
                    print(f"notify: failed ntfy for item_id={item.id}: {err}")
                else:
                    _set_notify_channel_sent(item, channel="ntfy")

            final_state = _get_notify_state(item)
            all_required_sent = (not wants_email or final_state["email_sent"]) and (
                not wants_ntfy or final_state["ntfy_sent"]
            )

            if sent_ok and all_required_sent:
                if debug:
                    print(f"notify: marked sent item_id={item.id}")
                item.notify_sent = True
                result.sent += 1
            else:
                result.failed += 1

        if dry_run:
            session.rollback()
        else:
            session.commit()

    return result


def _bootstrap_notification_settings(session: Session) -> int:
    existing = {row[0] for row in session.execute(select(NotificationSetting.type))}

    missing = [tp for tp in DEFAULT_NOTIFICATION_TYPES if tp not in existing]
    if not missing:
        return 0

    for item_type in missing:
        session.add(
            NotificationSetting(
                type=item_type,
                email_enabled=True,
                ntfy_enabled=True,
                ntfy_topic=None,
            )
        )

    return len(missing)


def _load_pending_items(
    session: Session, limit: int
) -> list[tuple[Item, NotificationSetting | None]]:
    stmt = (
        select(Item, NotificationSetting)
        .outerjoin(NotificationSetting, NotificationSetting.type == Item.type)
        .where(Item.notify_sent.is_(False))
        .order_by(Item.id.asc())
        .options(selectinload(Item.attachments))
    )
    rows = list(session.execute(stmt).all())
    fallback_max = datetime.max.replace(tzinfo=timezone.utc)

    decorated: list[tuple[datetime | None, tuple[Item, NotificationSetting | None]]] = [
        (_sent_at_for_item(row[0]), row) for row in rows
    ]
    decorated.sort(
        key=lambda entry: (
            entry[0] is None,
            entry[0] or fallback_max,
            entry[1][0].id,
        )
    )
    return [row for _, row in decorated[:limit]]


def _get_notify_state(item: Item) -> dict[str, bool]:
    raw = item.raw_json if isinstance(item.raw_json, dict) else {}
    notify = raw.get("_notify") if isinstance(raw.get("_notify"), dict) else {}
    return {
        "email_sent": bool(notify.get("email_sent")),
        "ntfy_sent": bool(notify.get("ntfy_sent")),
    }


def _set_notify_channel_sent(item: Item, channel: str) -> None:
    raw = dict(item.raw_json) if isinstance(item.raw_json, dict) else {}
    notify = dict(raw.get("_notify")) if isinstance(raw.get("_notify"), dict) else {}

    key = "email_sent" if channel == "email" else "ntfy_sent"
    notify[key] = True
    raw["_notify"] = notify
    item.raw_json = raw


def _read_email_config(settings: Settings) -> EmailConfig:
    port = settings.smtp_port
    to_raw = settings.email_to
    recipients = [part.strip() for part in to_raw.split(",") if part.strip()]

    return EmailConfig(
        host=settings.smtp_host or None,
        port=port,
        username=settings.smtp_username or None,
        password=settings.smtp_password or None,
        sender=settings.email_from or None,
        recipients=recipients,
        use_ssl=(
            settings.smtp_use_ssl
            if settings.smtp_use_ssl is not None
            else (port == 465)
        ),
        starttls=(
            settings.smtp_starttls
            if settings.smtp_starttls is not None
            else (port != 465)
        ),
    )


def _read_ntfy_config(settings: Settings) -> NtfyConfig:
    return NtfyConfig(
        url=settings.ntfy_url or None,
        default_topic=settings.ntfy_topic or None,
        token=settings.ntfy_token or None,
    )


def _send_email(
    item: Item, cfg: EmailConfig, s3_client=None, settings: Settings | None = None
) -> None:
    if not cfg.enabled:
        raise RuntimeError("email channel is not configured")

    msg = EmailMessage()
    msg["From"] = cfg.sender
    msg["To"] = ", ".join(cfg.recipients)
    msg["Subject"] = _subject_for(item)
    msg.set_content(_plain_text_for(item))

    if s3_client is not None and settings is not None:
        for att in item.attachments:
            if att.blob_key:
                try:
                    data = download_blob(
                        s3_client, settings.blob_s3_bucket, att.blob_key
                    )
                    content_type = att.content_type or guess_content_type(att.filename)
                    maintype, _, subtype = content_type.partition("/")
                    msg.add_attachment(
                        data, maintype=maintype, subtype=subtype, filename=att.filename
                    )
                except Exception as exc:
                    logger.warning(
                        "Could not attach blob %s to email: %s", att.blob_key, exc
                    )

    if cfg.use_ssl:
        server: smtplib.SMTP | smtplib.SMTP_SSL = smtplib.SMTP_SSL(
            cfg.host, cfg.port, timeout=30
        )
    else:
        server = smtplib.SMTP(cfg.host, cfg.port, timeout=30)

    try:
        if not cfg.use_ssl and cfg.starttls:
            server.starttls()
        if cfg.username:
            if not cfg.password:
                raise RuntimeError("SMTP_USERNAME is set but SMTP_PASSWORD is missing")
            server.login(cfg.username, cfg.password)
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def _send_ntfy(
    item: Item,
    cfg: NtfyConfig,
    topic: str,
    s3_client=None,
    settings: Settings | None = None,
) -> None:
    if not cfg.url:
        raise RuntimeError("ntfy url is missing")

    url = f"{cfg.url.rstrip('/')}/{topic}"
    headers = {
        "Title": _subject_for(item),
        "Tags": ",".join(_ntfy_tags_for_item(item)),
        "Markdown": "yes",
    }
    if cfg.token:
        headers["Authorization"] = f"Bearer {cfg.token}"

    # For photo items, attach the first image blob as a presigned URL so ntfy
    # displays it inline in the notification.
    if item.type == "photo" and s3_client is not None and settings is not None:
        for att in item.attachments:
            if att.blob_key:
                try:
                    presigned = generate_presigned_url(
                        s3_client, settings.blob_s3_bucket, att.blob_key
                    )
                    headers["Attach"] = presigned
                    headers["Filename"] = att.filename
                except Exception as exc:
                    logger.warning(
                        "Could not generate presigned URL for ntfy attachment %s: %s",
                        att.blob_key,
                        exc,
                    )
                break  # one photo attachment per notification

    response = requests.post(
        url,
        data=_ntfy_markdown_for(item).encode("utf-8"),
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()


def _with_retries(
    func: Callable[[], None],
    action: str,
    attempts: int = 3,
    base_delay_seconds: float = 1.0,
) -> tuple[bool, str | None]:
    last_error: str | None = None

    for attempt in range(1, attempts + 1):
        try:
            func()
            return True, None
        except Exception as exc:
            last_error = str(exc)
            if attempt >= attempts:
                break
            delay = base_delay_seconds * (2 ** (attempt - 1))
            print(
                f"notify: retrying {action} in {delay:.1f}s "
                f"(attempt {attempt + 1}/{attempts})"
            )
            time.sleep(delay)

    return False, last_error


def _subject_for(item: Item) -> str:
    title = _clean_text(item.title, default="(untitled)")
    item_type = _clean_text(item.type, default="item")
    return f"[Skoleintra:{item_type}] {title}"


def _plain_text_for(item: Item) -> str:
    title = _clean_text(item.title, default="(untitled)")
    sender = _clean_text(item.sender, default="unknown")
    item_type = _clean_text(item.type, default="item")
    body_txt = _body_text_from_html(item.body_html)

    lines = [
        f"Type: {item_type}",
        f"Title: {title}",
        f"Sender: {sender}",
    ]

    sent_at = _sent_at_for_item(item)
    if sent_at:
        lines.append(f"Date: {sent_at.isoformat()}")

    if body_txt:
        lines.append("")
        lines.append(body_txt)

    return "\n".join(lines)


def _ntfy_markdown_for(item: Item) -> str:
    title = _clean_text(item.title, default="(untitled)")
    sender = _clean_text(item.sender, default="unknown")
    item_type = _clean_text(item.type, default="item")
    body_txt = _body_text_from_html(item.body_html)

    meta_parts = [f"`{item_type}`", sender]
    sent_at = _sent_at_for_item(item)
    if sent_at:
        meta_parts.append(_format_mobile_date(sent_at.isoformat()))

    lines = [
        f"**{title}**",
        " • ".join(meta_parts),
    ]

    if body_txt:
        lines.append("")
        lines.append(body_txt)

    return "\n".join(lines)


def _ntfy_tags_for_item(item: Item) -> list[str]:
    item_type = _clean_text(item.type, default="item").lower()
    type_tags = {
        "message": ["email", "school"],
        "homework": ["books", "school"],
        "document": ["page_facing_up", "school"],
        "photo": ["camera", "school"],
        "weekplan": ["calendar", "school"],
    }
    return type_tags.get(item_type, ["bell", "school"])


def _body_text_from_html(body_html: str | None) -> str:
    if not body_html:
        return ""

    normalized = html.unescape(body_html).replace("\xa0", " ")
    soup = BeautifulSoup(normalized, "html.parser")

    for br in soup.find_all("br"):
        br.replace_with("\n")

    txt = soup.get_text("\n")
    lines = [_collapse_ws(line) for line in txt.splitlines()]
    return "\n".join(line for line in lines if line)


def _collapse_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _clean_text(value: str | None, default: str) -> str:
    if not value:
        return default
    normalized = html.unescape(value).replace("\xa0", " ")
    collapsed = _collapse_ws(normalized)
    return collapsed or default


def _format_mobile_date(iso_value: str) -> str:
    # Keep date compact for lock-screen and mobile notification layouts.
    return iso_value.replace("T", " ")[:16]


def _sent_at_for_item(item: Item) -> datetime | None:
    if isinstance(item.raw_json, dict):
        raw_date = item.raw_json.get("SentReceivedDateText")
        if isinstance(raw_date, str):
            parsed = _parse_portal_datetime(raw_date)
            if parsed is not None:
                return parsed

    if item.date is not None:
        return item.date

    return None


def _parse_portal_datetime(raw: str) -> datetime | None:
    value = raw.strip().replace("\xa0", " ")
    if not value:
        return None

    # ISO timestamps, e.g. 2025-10-21T12:31:00+00:00
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        pass

    # Danish style, e.g. 21. okt. 2025 12:31
    m = re.search(r"(\d{1,2})\.\s*(\w+\.?)\s*(\d{4})\s+(\d{2}):(\d{2})", value)
    if m:
        day, month_str, year, hour, minute = m.groups()
        month = _DA_MONTHS.get(month_str.rstrip(".").lower()[:3])
        if month is not None:
            try:
                return datetime(
                    int(year),
                    month,
                    int(day),
                    int(hour),
                    int(minute),
                    tzinfo=timezone.utc,
                )
            except ValueError:
                pass

    # Slash format, e.g. 21/10/2025 12:31
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2})", value)
    if m:
        dd, mm, year, hour, minute = m.groups()
        try:
            return datetime(
                int(year),
                int(mm),
                int(dd),
                int(hour),
                int(minute),
                tzinfo=timezone.utc,
            )
        except ValueError:
            return None

    return None
