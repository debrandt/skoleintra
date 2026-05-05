from contextlib import contextmanager
from types import SimpleNamespace

import skoleintra.scraper as scraper_module
from skoleintra.db.identity import ChildSnapshot
from skoleintra.scraper.models import ScrapedItem
from skoleintra.settings import Settings


def test_run_scrape_includes_weekplan_items(monkeypatch):
    upserted_types: list[str] = []

    class DummyPortal:
        def __init__(self, hostname: str, state_dir: str) -> None:
            self.hostname = hostname
            self.state_dir = state_dir

    @contextmanager
    def fake_session_scope():
        yield object()

    monkeypatch.setattr(scraper_module, "PortalSession", DummyPortal)
    monkeypatch.setattr(scraper_module, "get_s3_client", lambda settings: None)
    monkeypatch.setattr(scraper_module, "login", lambda *args, **kwargs: object())
    monkeypatch.setattr(
        scraper_module,
        "get_child_snapshots",
        lambda portal, soup: [
            ChildSnapshot(
                source_id="child-1",
                display_name="Freja Example",
                url_prefix="https://school.example.test/parent/1234/Freja",
            )
        ],
    )
    monkeypatch.setattr(scraper_module, "session_scope", fake_session_scope)
    monkeypatch.setattr(scraper_module, "prune_photo_blobs", lambda session, days: 0)
    monkeypatch.setattr(
        scraper_module,
        "sync_child_scope",
        lambda session, school_hostname, discovered, scope_succeeded: [
            SimpleNamespace(id=1, source_id="child-1")
        ],
    )
    monkeypatch.setattr(scraper_module.messages_scraper, "scrape", lambda *args: [])
    monkeypatch.setattr(scraper_module.photos_scraper, "scrape", lambda *args: [])
    monkeypatch.setattr(
        scraper_module.weekplans_scraper,
        "scrape",
        lambda *args: [
            ScrapedItem(
                type="weekplan",
                external_id="2026-W19",
                title="Ugeplan for Mellemtrin A - uge 19",
                sender="Mellemtrin A",
                body_html="<p>Bring boots.</p>",
                date=None,
            )
        ],
    )
    monkeypatch.setattr(
        scraper_module,
        "upsert_item",
        lambda session, child, scraped: (
            upserted_types.append(scraped.type) or SimpleNamespace(id=1),
            True,
        ),
    )
    monkeypatch.setattr(scraper_module, "upsert_attachment", lambda *args: None)
    monkeypatch.setattr(scraper_module, "download_pending_attachments", lambda *args: 0)

    result = scraper_module.run_scrape(
        Settings(
            database_url="postgresql+psycopg://localhost/skoleintra",
            hostname="school.example.test",
            username="parent",
            password="secret",
        )
    )

    assert upserted_types == ["weekplan"]
    assert result.items_new == 1
    assert result.items_updated == 0
