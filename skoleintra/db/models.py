from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Child(Base):
    __tablename__ = "children"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    school_hostname: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    items: Mapped[list["Item"]] = relationship(back_populates="child", cascade="all, delete-orphan")


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    child_id: Mapped[Optional[int]] = mapped_column(ForeignKey("children.id"), nullable=True)
    child: Mapped[Optional[Child]] = relationship(back_populates="items")

    type: Mapped[str] = mapped_column(Text, nullable=False)          # message/homework/document/photo/weekplan/...
    external_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sender: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    body_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    date: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    notify_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    raw_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("child_id", "type", "external_id", name="uq_item_child_type_external"),
    )


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    item: Mapped[Item] = relationship(back_populates="attachments")

    filename: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    local_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NotificationSetting(Base):
    __tablename__ = "notification_settings"

    # type acts like a key: "message", "homework", ...
    type: Mapped[str] = mapped_column(Text, primary_key=True)

    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    ntfy_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    ntfy_topic: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
