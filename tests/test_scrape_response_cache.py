from pathlib import Path

import requests

from skoleintra.scraper.pages import messages as messages_scraper
from skoleintra.scraper.pages import photos as photos_scraper
from skoleintra.scraper.pages import weekplans as weekplans_scraper
from skoleintra.scraper.session import PortalSession


def _response(url: str, body: str) -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response.url = url
    response._content = body.encode("utf-8")  # pylint: disable=protected-access
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    response.encoding = "utf-8"
    return response


def test_photo_scrape_reuses_cached_album_pages_across_runs(tmp_path, monkeypatch):
    albums_html = """
        <ul id="sk-photos-albums-content-container" class="sk-list padding-15">
            <li>
                <a href="/parent/9999/Child/photos/albums/album/photos/6254" class="sk-photoalbums-list-item">
                    <div class="sk-photoalbum-list-item-title">Classroom week 19</div>
                    <div class="sk-photoalbum-list-item-description">Outdoor crafts.</div>
                    <div class="sk-photoalbum-list-item-author">Oprettet af: Teacher Example</div>
                </a>
            </li>
        </ul>
    """
    album_html = """
        <div class="sk-photoalbums" data-clientlogic-settings-PhotoAlbum='{"GalleryModel":{"Items":[
            {"Source":"/file/photoalbum/6254/IMG_1001.jpeg?t=1","Description":"IMG_1001.jpeg"}
        ]}}'></div>
        <div class="h-ta-c">Classroom week 19</div>
    """
    counts: dict[str, int] = {}

    def fake_get(self, url, **kwargs):  # pylint: disable=unused-argument
        counts[url] = counts.get(url, 0) + 1
        if url.endswith("/photos/albums"):
            return _response(url, albums_html)
        if url.endswith("/photos/albums/album/photos/6254"):
            return _response(url, album_html)
        raise AssertionError(url)

    monkeypatch.setattr(requests.Session, "get", fake_get)

    state_dir = str(tmp_path / "state")
    child_url_prefix = "https://example.test/parent/9999/Child"

    first_portal = PortalSession("example.test", state_dir)
    second_portal = PortalSession("example.test", state_dir)

    first_items = photos_scraper.scrape(
        first_portal, child_url_prefix, cache_ttl_seconds=900
    )
    second_items = photos_scraper.scrape(
        second_portal, child_url_prefix, cache_ttl_seconds=900
    )

    assert len(first_items) == 2
    assert len(second_items) == 2
    assert counts == {
        f"{child_url_prefix}/photos/albums": 2,
        f"{child_url_prefix}/photos/albums/album/photos/6254": 1,
    }
    cache_files = list((Path(state_dir) / "response-cache").glob("*"))
    assert cache_files


def test_message_scrape_reuses_cached_thread_pages_across_runs(tmp_path, monkeypatch):
    messages_html = """
        <div class="sk-l-content-wrapper">
            <div data-messages='{"Conversations":[{"ThreadId":"thread-1","LatestMessageId":"1001"}]}'></div>
        </div>
    """
    thread_html = """
        [{"Id":"1001","Subject":"Hello","SenderName":"Teacher Example","BaseText":"Hi there","PreviousMessagesText":"","SentReceivedDateText":"05/05/2026 12:00","AttachmentsLinks":[]}]
    """
    counts: dict[str, int] = {}

    def fake_get(self, url, **kwargs):  # pylint: disable=unused-argument
        counts[url] = counts.get(url, 0) + 1
        if url.endswith("/messages/conversations"):
            return _response(url, messages_html)
        if "loadmessagesforselectedconversation" in url:
            return _response(url, thread_html)
        raise AssertionError(url)

    monkeypatch.setattr(requests.Session, "get", fake_get)

    state_dir = str(tmp_path / "state")
    child_url_prefix = "https://example.test/parent/9999/Child"

    first_portal = PortalSession("example.test", state_dir)
    second_portal = PortalSession("example.test", state_dir)

    first_items = messages_scraper.scrape(
        first_portal, child_url_prefix, cache_ttl_seconds=900
    )
    second_items = messages_scraper.scrape(
        second_portal, child_url_prefix, cache_ttl_seconds=900
    )

    assert [item.external_id for item in first_items] == ["thread-1--1001"]
    assert [item.external_id for item in second_items] == ["thread-1--1001"]
    assert counts == {
        f"{child_url_prefix}/messages/conversations": 2,
        f"{child_url_prefix}/messages/conversations/loadmessagesforselectedconversation?threadId=thread-1&takeFromRootMessageId=1001&takeToMessageId=0&searchRequest=": 1,
    }


def test_weekplan_scrape_reuses_cached_detail_pages_across_runs(tmp_path, monkeypatch):
    list_html = """
        <ul class="sk-weekly-plans-list-container">
            <li>
                <a href="/parent/9999/Childitem/weeklyplansandhomework/item/class/19-2026">Uge 19</a>
            </li>
        </ul>
    """
    detail_html = """
        <div id="root" data-clientlogic-settings-weeklyplansapp='{"SelectedPlan":{
            "FormattedWeek":"19-2026",
            "ClassOrGroup":"Class Blue",
            "DailyPlans":[{"Day":"Mandag","Date":"2026-05-04","LessonPlans":[{"Content":"Bring boots.","Subject":{"Title":"Tur"},"Attachments":[],"IsDraft":false}]}],
            "Attachments":[]
        }}'></div>
    """
    counts: dict[str, int] = {}

    def fake_get(self, url, **kwargs):  # pylint: disable=unused-argument
        counts[url] = counts.get(url, 0) + 1
        if url.endswith("item/weeklyplansandhomework/list"):
            return _response(url, list_html)
        if url.endswith("item/weeklyplansandhomework/item/class/19-2026"):
            return _response(url, detail_html)
        raise AssertionError(url)

    monkeypatch.setattr(requests.Session, "get", fake_get)

    state_dir = str(tmp_path / "state")
    child_url_prefix = "https://example.test/parent/9999/Child"

    first_portal = PortalSession("example.test", state_dir)
    second_portal = PortalSession("example.test", state_dir)

    first_items = weekplans_scraper.scrape(
        first_portal, child_url_prefix, cache_ttl_seconds=900
    )
    second_items = weekplans_scraper.scrape(
        second_portal, child_url_prefix, cache_ttl_seconds=900
    )

    assert [item.external_id for item in first_items] == ["2026-W19"]
    assert [item.external_id for item in second_items] == ["2026-W19"]
    assert counts == {
        f"{child_url_prefix}item/weeklyplansandhomework/list": 2,
        f"{child_url_prefix}item/weeklyplansandhomework/item/class/19-2026": 1,
    }
