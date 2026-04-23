from datetime import datetime, timezone

import pytest
from bs4 import BeautifulSoup

from skoleintra.photos.service import parse_not_older_than_date
from skoleintra.scraper.pages.photos import (
    _album_author,
    _album_description,
    _album_external_id,
    _album_title,
    _extract_date,
    _extract_image_urls,
)


def test_parse_not_older_than_date_valid():
    dt = parse_not_older_than_date("2026-04-01")
    assert dt == datetime(2026, 4, 1, tzinfo=timezone.utc)


def test_parse_not_older_than_date_empty():
    assert parse_not_older_than_date("") is None
    assert parse_not_older_than_date(None) is None


def test_parse_not_older_than_date_invalid():
    with pytest.raises(ValueError):
        parse_not_older_than_date("01-04-2026")


def test_extract_date_from_folder_name_dd_mm_yyyy():
    dt = _extract_date("Album 03.04.2026", BeautifulSoup("<div></div>", "lxml"))
    assert dt == datetime(2026, 4, 3, tzinfo=timezone.utc)


def test_extract_date_from_folder_name_iso():
    dt = _extract_date("Album 2026-04-03", BeautifulSoup("<div></div>", "lxml"))
    assert dt == datetime(2026, 4, 3, tzinfo=timezone.utc)


def test_album_metadata_and_photo_image_filtering():
        html = """
        <a class="sk-photoalbums-list-item" href="/parent/5798/Iben/photos/albums/album/photos/6216">
            <div class="sk-photoalbum-list-item-title">Valmuestuen uge 17</div>
            <div class="sk-photoalbum-list-item-description">Album beskrivelse</div>
            <div class="sk-photoalbum-list-item-author">Oprettet af: Karina Frederiksen</div>
        </a>
        <div>
            <img src="https://nsistatics.m.skoleintra.dk/logo.svg" />
            <img src="/file/photoalbum/6216/1000011430.jpg?t=123" />
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        album_link = soup.select_one("a.sk-photoalbums-list-item")
        assert album_link is not None
        assert _album_title(album_link) == "Valmuestuen uge 17"
        assert _album_description(album_link) == "Album beskrivelse"
        assert _album_author(album_link) == "Karina Frederiksen"
        assert _album_external_id("/parent/5798/Iben/photos/albums/album/photos/6216") == "6216"

        class DummyPortal:
                def abs_url(self, path: str) -> str:
                        if path.startswith("http"):
                                return path
                        return f"https://example.test{path}"

        urls = _extract_image_urls(soup, DummyPortal())
        assert urls == ["https://example.test/file/photoalbum/6216/1000011430.jpg?t=123"]
