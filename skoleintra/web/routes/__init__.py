from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from skoleintra.db.models import Attachment, Child, Item, NotificationSetting
from skoleintra.db.session import SessionLocal
from skoleintra.notifications.dispatcher import DEFAULT_NOTIFICATION_TYPES

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_notification_settings(db: Session) -> None:
    types_from_items = {
        row[0]
        for row in db.execute(select(Item.type).distinct())
        if row[0]
    }
    desired_types = set(DEFAULT_NOTIFICATION_TYPES) | types_from_items

    existing = {
        row[0]
        for row in db.execute(select(NotificationSetting.type))
    }
    missing = desired_types - existing
    if not missing:
        return

    for item_type in sorted(missing):
        db.add(
            NotificationSetting(
                type=item_type,
                email_enabled=True,
                ntfy_enabled=True,
                ntfy_topic=None,
            )
        )
    db.commit()


@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    total_items = db.scalar(select(func.count()).select_from(Item)) or 0
    unread_items = db.scalar(
        select(func.count()).select_from(Item).where(Item.is_read.is_(False))
    ) or 0
    pending_notifications = db.scalar(
        select(func.count()).select_from(Item).where(Item.notify_sent.is_(False))
    ) or 0

    latest_stmt = (
        select(Item)
        .options(joinedload(Item.child))
        .order_by(Item.date.desc().nullslast(), Item.id.desc())
        .limit(10)
    )
    latest_items = list(db.scalars(latest_stmt).all())

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "total_items": total_items,
            "unread_items": unread_items,
            "pending_notifications": pending_notifications,
            "latest_items": latest_items,
        },
    )


@router.get("/items")
def list_items(
    request: Request,
    db: Session = Depends(get_db),
    child_id: int | None = Query(default=None),
    item_type: str | None = Query(default=None, alias="type"),
    unread: bool = Query(default=False),
    q: str | None = Query(default=None),
    sort: str = Query(default="date_desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
):
    stmt = select(Item).options(joinedload(Item.child))

    if child_id is not None:
        stmt = stmt.where(Item.child_id == child_id)
    if item_type:
        stmt = stmt.where(Item.type == item_type)
    if unread:
        stmt = stmt.where(Item.is_read.is_(False))
    if q:
        needle = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Item.title.ilike(needle),
                Item.sender.ilike(needle),
                Item.body_html.ilike(needle),
            )
        )

    if sort == "date_asc":
        stmt = stmt.order_by(Item.date.asc().nullsfirst(), Item.id.asc())
    elif sort == "title_asc":
        stmt = stmt.order_by(Item.title.asc(), Item.id.desc())
    elif sort == "title_desc":
        stmt = stmt.order_by(Item.title.desc(), Item.id.desc())
    else:
        sort = "date_desc"
        stmt = stmt.order_by(Item.date.desc().nullslast(), Item.id.desc())

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    pages = max(1, (total + page_size - 1) // page_size)
    if page > pages:
        page = pages

    offset = (page - 1) * page_size
    items = list(db.scalars(stmt.offset(offset).limit(page_size)).all())
    children = list(db.scalars(select(Child).order_by(Child.name.asc())).all())
    item_types = [
        row[0]
        for row in db.execute(select(Item.type).distinct().order_by(Item.type.asc()))
        if row[0]
    ]

    return templates.TemplateResponse(
        request,
        "items.html",
        {
            "items": items,
            "children": children,
            "item_types": item_types,
            "filters": {
                "child_id": child_id,
                "type": item_type or "",
                "unread": unread,
                "q": q or "",
                "sort": sort,
                "page": page,
                "page_size": page_size,
            },
            "pagination": {
                "page": page,
                "pages": pages,
                "page_size": page_size,
                "total": total,
            },
        },
    )


@router.get("/items/{item_id}")
def item_detail(request: Request, item_id: int, db: Session = Depends(get_db)):
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    child = db.get(Child, item.child_id)
    attachments = list(
        db.scalars(
            select(Attachment)
            .where(Attachment.item_id == item.id)
            .order_by(Attachment.filename.asc())
        ).all()
    )

    return templates.TemplateResponse(
        request,
        "item_detail.html",
        {
            "item": item,
            "child": child,
            "attachments": attachments,
        },
    )


@router.post("/items/{item_id}/read")
def set_item_read(
    request: Request,
    item_id: int,
    db: Session = Depends(get_db),
    read: bool | None = Form(default=None),
):
    item = db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    item.is_read = (not item.is_read) if read is None else bool(read)
    db.commit()

    target = request.headers.get("referer") or "/items"
    return RedirectResponse(url=target, status_code=303)


@router.get("/settings/notifications")
def notification_settings_page(request: Request, db: Session = Depends(get_db)):
    _ensure_notification_settings(db)
    rows = list(
        db.scalars(
            select(NotificationSetting).order_by(NotificationSetting.type.asc())
        ).all()
    )
    return templates.TemplateResponse(
        request,
        "notification_settings.html",
        {
            "settings": rows,
        },
    )


@router.post("/settings/notifications")
async def save_notification_settings(request: Request, db: Session = Depends(get_db)):
    _ensure_notification_settings(db)
    form = await request.form()

    rows = list(
        db.scalars(
            select(NotificationSetting).order_by(NotificationSetting.type.asc())
        ).all()
    )

    for row in rows:
        key = row.type
        row.email_enabled = f"email_{key}" in form
        row.ntfy_enabled = f"ntfy_{key}" in form

        topic_key = f"topic_{key}"
        topic_val = str(form.get(topic_key, "")).strip()
        row.ntfy_topic = topic_val or None

    db.commit()
    return RedirectResponse(url="/settings/notifications", status_code=303)


@router.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"ok": True}

