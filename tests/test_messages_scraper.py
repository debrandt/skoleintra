"""Unit tests for the messages scraper — pure logic, no network/DB needed."""

from datetime import datetime, timezone

import pytest

from skoleintra.scraper.pages.messages import _parse_date, _msg_to_scraped_item


class TestParseDate:
    def test_danish_long_format(self):
        dt = _parse_date("15. jan. 2024 13:45")
        assert dt == datetime(2024, 1, 15, 13, 45, tzinfo=timezone.utc)

    def test_danish_short_month(self):
        dt = _parse_date("3. okt. 2023 09:00")
        assert dt == datetime(2023, 10, 3, 9, 0, tzinfo=timezone.utc)

    def test_iso_format(self):
        dt = _parse_date("15/01/2024 13:45")
        assert dt == datetime(2024, 1, 15, 13, 45, tzinfo=timezone.utc)

    def test_none_input(self):
        assert _parse_date(None) is None

    def test_empty_string(self):
        assert _parse_date("") is None

    def test_unparseable_string(self):
        assert _parse_date("ikke en dato") is None

    def test_nbsp_stripped(self):
        dt = _parse_date("15.\u00a0jan.\u00a02024 13:45")
        assert dt == datetime(2024, 1, 15, 13, 45, tzinfo=timezone.utc)


class TestMsgToScrapedItem:
    def _base_msg(self, **kwargs):
        msg = {
            "Id": 42,
            "Subject": "Test subject",
            "SenderName": "Alice",
            "BaseText": "<p>Hello</p>",
            "PreviousMessagesText": "",
            "SentReceivedDateText": "15. jan. 2024 13:45",
            "AttachmentsLinks": [],
        }
        msg.update(kwargs)
        return msg

    def test_basic_item(self):
        item = _msg_to_scraped_item(self._base_msg(), thread_id="t1")
        assert item is not None
        assert item.external_id == "t1--42"
        assert item.title == "Test subject"
        assert item.sender == "Alice"
        assert '<div class="base"><p>Hello</p></div>' in item.body_html
        assert item.date == datetime(2024, 1, 15, 13, 45, tzinfo=timezone.utc)
        assert item.type == "message"
        assert item.attachments == []

    def test_no_thread_id(self):
        item = _msg_to_scraped_item(self._base_msg(), thread_id="")
        assert item is not None
        assert item.external_id == "42"

    def test_missing_id_returns_none(self):
        msg = self._base_msg(Id=None)
        item = _msg_to_scraped_item(msg, thread_id="t1")
        assert item is None

    def test_previous_messages_appended(self):
        msg = self._base_msg(PreviousMessagesText="<p>old</p>")
        item = _msg_to_scraped_item(msg, thread_id="t1")
        assert item is not None
        assert '<div class="prev"><p>old</p></div>' in item.body_html

    def test_attachments_parsed(self):
        msg = self._base_msg(
            AttachmentsLinks=[
                {"HrefAttributeValue": "https://example.com/file.pdf", "Text": "file.pdf"}
            ]
        )
        item = _msg_to_scraped_item(msg, thread_id="t1")
        assert item is not None
        assert len(item.attachments) == 1
        assert item.attachments[0].url == "https://example.com/file.pdf"
        assert item.attachments[0].filename == "file.pdf"

    def test_html_entities_decoded_for_storage(self):
        msg = self._base_msg(
            Subject="M&oslash;de med for&aelig;ldre",
            SenderName="P&aelig;dagog&nbsp;Anne",
            BaseText="<p>Velkommen&nbsp;til m&oslash;det</p>",
        )
        item = _msg_to_scraped_item(msg, thread_id="t1")
        assert item is not None
        assert item.title == "Møde med forældre"
        assert item.sender == "Pædagog Anne"
        assert "Velkommen til mødet" in item.body_html
