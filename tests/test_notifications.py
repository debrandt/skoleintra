from types import SimpleNamespace

from skoleintra.db.models import Attachment, Item
from skoleintra.notifications import dispatcher
from skoleintra.notifications.dispatcher import (
    EMAIL_INLINE_ATTACHMENT_MAX_BYTES,
    EmailConfig,
    _ntfy_markdown_for,
    _plain_text_for,
    _send_email,
    _subject_for,
)


def test_photo_album_notifications_use_domain_label():
    item = Item(
        type="photo_album",
        title="Photo album: Classroom week 19",
        sender="Teacher Example",
        body_html="<p>Classroom week 19</p><p>Photos: 2</p><p>Outdoor crafts.</p>",
    )

    assert (
        _subject_for(item) == "[Skoleintra:photo album] Photo album: Classroom week 19"
    )
    assert _ntfy_markdown_for(item).splitlines()[:2] == [
        "**Photo album: Classroom week 19**",
        "`photo album` • Teacher Example",
    ]


def test_message_notification_text_uses_presigned_attachment_links(monkeypatch):
    item = Item(
        type="message",
        title="Homework details",
        sender="Teacher Example",
        body_html="<p>Read chapter 4.</p>",
    )
    item.attachments = [
        Attachment(
            filename="worksheet.pdf",
            url="https://portal.example/worksheet.pdf",
            blob_key="child/message/worksheet.pdf",
        )
    ]

    monkeypatch.setattr(
        dispatcher,
        "generate_presigned_url",
        lambda s3_client, bucket, key: f"https://blob.example/{bucket}/{key}",
    )
    settings = SimpleNamespace(blob_s3_bucket="private-bucket")

    plain = _plain_text_for(item, s3_client=object(), settings=settings)
    assert "Attachments:" in plain
    assert (
        "worksheet.pdf: https://blob.example/private-bucket/child/message/worksheet.pdf"
        in plain
    )

    markdown = _ntfy_markdown_for(item, s3_client=object(), settings=settings)
    assert "Attachments:" in markdown
    assert (
        "- worksheet.pdf: https://blob.example/private-bucket/child/message/worksheet.pdf"
        in markdown
    )


def test_email_only_inlines_small_attachments(monkeypatch):
    sent_messages = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        def send_message(self, msg):
            sent_messages.append(msg)

        def quit(self):
            return None

    monkeypatch.setattr(dispatcher.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(
        dispatcher,
        "download_blob",
        lambda s3_client, bucket, key: f"{bucket}:{key}".encode("utf-8"),
    )

    item = Item(
        type="message",
        title="Files",
        sender="Teacher Example",
        body_html="<p>Please review.</p>",
    )
    item.attachments = [
        Attachment(
            filename="small.pdf",
            url="https://portal.example/small.pdf",
            blob_key="small.pdf",
            content_type="application/pdf",
            size_bytes=1024,
        ),
        Attachment(
            filename="large.pdf",
            url="https://portal.example/large.pdf",
            blob_key="large.pdf",
            content_type="application/pdf",
            size_bytes=EMAIL_INLINE_ATTACHMENT_MAX_BYTES + 1,
        ),
    ]

    cfg = EmailConfig(
        host="smtp.example",
        port=25,
        username=None,
        password=None,
        sender="noreply@example.com",
        recipients=["parent@example.com"],
        use_ssl=False,
        starttls=False,
    )
    settings = SimpleNamespace(blob_s3_bucket="private-bucket")

    _send_email(item=item, cfg=cfg, s3_client=object(), settings=settings)

    assert len(sent_messages) == 1
    attached_names = [part.get_filename() for part in sent_messages[0].iter_attachments()]
    assert attached_names == ["small.pdf"]
