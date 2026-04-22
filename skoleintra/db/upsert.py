"""DB upsert helpers for scraped data.

Each helper performs an INSERT … ON CONFLICT DO UPDATE (upsert) so that
re-running the scraper is idempotent.
"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from skoleintra.db.models import Attachment, Child, Item
from skoleintra.scraper.models import ScrapedItem


def upsert_child(session: Session, name: str, school_hostname: str) -> Child:
    """Upsert a child record and return the ORM instance."""
    stmt = (
        pg_insert(Child)
        .values(name=name, school_hostname=school_hostname)
        .on_conflict_do_update(
            constraint="uq_child_name_hostname",
            set_={"school_hostname": school_hostname},
        )
        .returning(Child.id)
    )
    row = session.execute(stmt).fetchone()
    assert row is not None
    child = session.get(Child, row[0])
    assert child is not None
    return child


def upsert_item(
    session: Session,
    child: Child,
    scraped: "ScrapedItem",
) -> tuple[Item, bool]:
    """Upsert an item and return ``(item, is_new)``.

    ``is_new`` is True when the row was inserted (not updated).
    Newly inserted items have ``notify_sent=False`` so the notification
    dispatcher will pick them up.
    """
    stmt = (
        pg_insert(Item)
        .values(
            child_id=child.id,
            type=scraped.type,
            external_id=scraped.external_id,
            title=scraped.title,
            sender=scraped.sender,
            body_html=scraped.body_html,
            date=scraped.date,
            is_read=False,
            notify_sent=False,
            raw_json=scraped.raw_json,
        )
        .on_conflict_do_update(
            constraint="uq_item_child_type_external",
            set_={
                "title": scraped.title,
                "sender": scraped.sender,
                "body_html": scraped.body_html,
                "date": scraped.date,
                "raw_json": scraped.raw_json,
            },
        )
        .returning(Item.id)
    )
    # Track whether a row already existed before this upsert
    existing = session.execute(
        select(Item.id).where(
            Item.child_id == child.id,
            Item.type == scraped.type,
            Item.external_id == scraped.external_id,
        )
    ).fetchone()
    is_new = existing is None

    row = session.execute(stmt).fetchone()
    assert row is not None
    item = session.get(Item, row[0])
    assert item is not None
    return item, is_new


def upsert_attachment(
    session: Session,
    item: Item,
    filename: str,
    url: str,
) -> Attachment:
    """Upsert an attachment record and return the ORM instance."""
    stmt = (
        pg_insert(Attachment)
        .values(item_id=item.id, filename=filename, url=url)
        .on_conflict_do_update(
            constraint="uq_attachment_item_url",
            set_={"filename": filename},
        )
        .returning(Attachment.id)
    )
    row = session.execute(stmt).fetchone()
    assert row is not None
    att = session.get(Attachment, row[0])
    assert att is not None
    return att
