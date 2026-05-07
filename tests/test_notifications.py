from email.message import EmailMessage

from skoleintra.db.models import Attachment, Item
from skoleintra.notifications import dispatcher
from skoleintra.notifications.dispatcher import (
    EmailConfig,
    NtfyConfig,
    _ntfy_markdown_for,
    _plain_text_for,
    _send_email,
    _subject_for,
)
from skoleintra.settings import Settings


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


def test_message_notifications_only_include_new_message_content():
    item = Item(
        type="message",
        title="Re: Parent meeting",
        sender="Teacher Example",
        body_html=(
            '<div class="base"><p>Latest update only.</p></div>\n'
            '<div class="prev"><p>Older thread context.</p></div>\n'
        ),
        message_body_html="<p>Latest update only.</p>",
        message_quoted_body_html="<p>Older thread context.</p>",
    )

    plain_text = _plain_text_for(item)
    ntfy_markdown = _ntfy_markdown_for(item)

    assert "Latest update only." in plain_text
    assert "Older thread context." not in plain_text
    assert "Latest update only." in ntfy_markdown
    assert "Older thread context." not in ntfy_markdown


def test_message_email_uses_links_for_large_attachments_and_embeds_small_files(
    monkeypatch,
):
    sent_messages: list[EmailMessage] = []

    class FakeSMTP:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def send_message(self, message: EmailMessage) -> None:
            sent_messages.append(message)

        def quit(self) -> None:
            return None

    item = Item(
        type="message",
        title="Re: Parent meeting",
        sender="Teacher Example",
        body_html="<p>Fallback body.</p>",
        message_body_html="<p>Latest update only.</p>",
        attachments=[
            Attachment(
                filename="agenda.pdf",
                url="https://portal.example.test/agenda.pdf",
                blob_key="messages/agenda.pdf",
                size_bytes=1024,
                content_type="application/pdf",
            ),
            Attachment(
                filename="recording.zip",
                url="https://portal.example.test/recording.zip",
                blob_key="messages/recording.zip",
                size_bytes=6 * 1024 * 1024,
                content_type="application/zip",
            ),
        ],
    )
    cfg = EmailConfig(
        host="smtp.example.test",
        port=25,
        username=None,
        password=None,
        sender="school@example.test",
        recipients=["parent@example.test"],
        use_ssl=False,
        starttls=False,
    )
    settings = Settings(blob_s3_bucket="private-bucket")

    monkeypatch.setattr(dispatcher.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(
        dispatcher,
        "generate_presigned_url",
        lambda _client, _bucket, key: f"https://blob.example.test/{key}",
    )
    monkeypatch.setattr(
        dispatcher,
        "download_blob",
        lambda _client, _bucket, key: f"payload:{key}".encode("utf-8"),
    )

    _send_email(item=item, cfg=cfg, s3_client=object(), settings=settings)

    assert len(sent_messages) == 1
    sent = sent_messages[0]
    plain_part = sent.get_body(preferencelist=("plain",))
    assert plain_part is not None
    plain_text = plain_part.get_content()
    assert "Latest update only." in plain_text
    assert "https://blob.example.test/messages/agenda.pdf" in plain_text
    assert "https://blob.example.test/messages/recording.zip" in plain_text
    attachment_filenames = [
        part.get_filename() for part in sent.iter_attachments() if part.get_filename()
    ]
    assert attachment_filenames == ["agenda.pdf"]


def test_message_ntfy_includes_presigned_attachment_links(monkeypatch):
    posted: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    item = Item(
        type="message",
        title="Re: Parent meeting",
        sender="Teacher Example",
        body_html="<p>Fallback body.</p>",
        message_body_html="<p>Latest update only.</p>",
        attachments=[
            Attachment(
                filename="agenda.pdf",
                url="https://portal.example.test/agenda.pdf",
                blob_key="messages/agenda.pdf",
                size_bytes=1024,
                content_type="application/pdf",
            )
        ],
    )
    cfg = NtfyConfig(
        url="https://ntfy.example.test",
        default_topic="family-topic",
        token=None,
    )
    settings = Settings(blob_s3_bucket="private-bucket")

    monkeypatch.setattr(
        dispatcher,
        "generate_presigned_url",
        lambda _client, _bucket, key: f"https://blob.example.test/{key}",
    )
    monkeypatch.setattr(
        dispatcher.requests,
        "post",
        lambda url, data, headers, timeout: posted.update(
            {
                "url": url,
                "data": data.decode("utf-8"),
                "headers": headers,
                "timeout": timeout,
            }
        )
        or FakeResponse(),
    )

    dispatcher._send_ntfy(
        item=item,
        cfg=cfg,
        topic="family-topic",
        s3_client=object(),
        settings=settings,
    )

    assert posted["url"] == "https://ntfy.example.test/family-topic"
    assert "Latest update only." in str(posted["data"])
    assert "https://blob.example.test/messages/agenda.pdf" in str(posted["data"])
