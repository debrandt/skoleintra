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
    scrape,
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
    assert (
        _album_external_id("/parent/5798/Iben/photos/albums/album/photos/6216")
        == "6216"
    )

    class DummyPortal:
        def abs_url(self, path: str) -> str:
            if path.startswith("http"):
                return path
            return f"https://example.test{path}"

    urls = _extract_image_urls(soup, DummyPortal())
    assert urls == ["https://example.test/file/photoalbum/6216/1000011430.jpg?t=123"]


def test_scrape_returns_photo_album_and_individual_photos():
    albums_html = """
        <ul id="sk-photos-albums-content-container" class="sk-list padding-15">
            <li>
                <div>
                    <div class="h-fl-l h-width-90">
                        <a href="/parent/9999/Child/photos/albums/album/photos/6254" class="sk-photoalbums-list-item">
                            <div class="sk-photoalbum-list-item-cover-image">
                                <div style="background : url('/file/photoalbum/6254/IMG_1001.jpeg?t=1');"></div>
                            </div>
                            <div class="sk-photoalbum-list-item-description-block">
                                <div class="sk-photoalbum-list-item-title">
                                    Classroom week 19
                                </div>
                                <div class="sk-photoalbum-list-item-description">
                                    Outdoor crafts and forest snacks.
                                </div>
                                <div class="sk-photoalbum-list-item-author">Oprettet af: Teacher Example</div>
                            </div>
                        </a>
                    </div>
                </div>
            </li>
        </ul>
    """
    album_html = """
        <div class="sk-photoalbums" data-clientlogic-settings-PhotoAlbum='{"GalleryModel":{"Items":[
            {"Source":"/file/photoalbum/6254/IMG_1001.jpeg?t=1","Description":"IMG_1001.jpeg"},
            {"Source":"/file/photoalbum/6254/IMG_1002.jpeg?t=2","Description":"IMG_1002.jpeg"}
        ]}}'></div>
        <div class="h-ta-c">Classroom week 19</div>
        <div class="h-ta-c">Group Blue</div>
        <div class="sk-photoalbums-list">
            <ul class="h-hlist">
                <li>
                    <div class="sk-photoalbum-image-thumbnail">
                        <div>
                            <a href="/parent/9999/Child/photos/albums/album/6254/0?category=Group+Blue">
                                <img src="/file/photoalbum/6254/IMG_1001.jpeg?t=1"/>
                            </a>
                        </div>
                    </div>
                </li>
                <li>
                    <div class="sk-photoalbum-image-thumbnail">
                        <div>
                            <a href="/parent/9999/Child/photos/albums/album/6254/1?category=Group+Blue">
                                <img src="/file/photoalbum/6254/IMG_1002.jpeg?t=2"/>
                            </a>
                        </div>
                    </div>
                </li>
            </ul>
        </div>
    """

    class DummyResponse:
        def __init__(self, text: str) -> None:
            self.text = text

    class DummyPortal:
        def get(self, url: str, **_kwargs) -> DummyResponse:
            if url.endswith("/photos/albums"):
                return DummyResponse(albums_html)
            if url.endswith("/photos/albums/album/photos/6254"):
                return DummyResponse(album_html)
            raise AssertionError(url)

        def abs_url(self, path: str) -> str:
            if path.startswith("http"):
                return path
            return f"https://example.test{path}"

    items = scrape(DummyPortal(), "https://example.test/parent/9999/Child")

    assert [item.type for item in items] == ["photo_album", "photo", "photo"]
    assert items[0].external_id == "6254"
    assert items[0].title == "Photo album: Classroom week 19"
    assert items[0].sender == "Teacher Example"
    assert items[0].raw_json == {
        "album_url": "https://example.test/parent/9999/Child/photos/albums/album/photos/6254",
        "count": 2,
        "description": "Outdoor crafts and forest snacks.",
        "author": "Teacher Example",
    }
    assert items[1].external_id == (
        "6254:https://example.test/file/photoalbum/6254/IMG_1001.jpeg?t=1"
    )
    assert items[1].title == "Photo: Classroom week 19"
    assert items[1].attachments[0].url == (
        "https://example.test/file/photoalbum/6254/IMG_1001.jpeg?t=1"
    )
    assert items[2].external_id == (
        "6254:https://example.test/file/photoalbum/6254/IMG_1002.jpeg?t=2"
    )


def test_extract_image_urls_uses_gallery_model_items():
    html = """
        <div class="sk-photoalbums" data-clientlogic-settings-PhotoAlbum='{"GalleryModel":{"Items":[
            {"Source":"/file/photoalbum/6254/IMG_1001.jpeg?t=1","Description":"IMG_1001.jpeg"},
            {"Source":"/file/photoalbum/6254/IMG_1002.jpeg?t=2","Description":"IMG_1002.jpeg"}
        ]}}'></div>
    """
    soup = BeautifulSoup(html, "lxml")

    class DummyPortal:
        def abs_url(self, path: str) -> str:
            if path.startswith("http"):
                return path
            return f"https://example.test{path}"

    assert _extract_image_urls(soup, DummyPortal()) == [
        "https://example.test/file/photoalbum/6254/IMG_1001.jpeg?t=1",
        "https://example.test/file/photoalbum/6254/IMG_1002.jpeg?t=2",
    ]
