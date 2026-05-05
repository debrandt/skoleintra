from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    school_hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("name", "school_hostname", name="uq_child_name_hostname"),
    )

    items: Mapped[list["Item"]] = relationship("Item", back_populates="child")


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    child_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("children.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    sender: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    body_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notify_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "child_id", "type", "external_id", name="uq_item_child_type_external"
        ),
    )

    child: Mapped["Child"] = relationship("Child", back_populates="items")
    attachments: Mapped[list["Attachment"]] = relationship(
        "Attachment", back_populates="item"
    )


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    url: Mapped[str] = mapped_column(Text, nullable=False)
    blob_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("item_id", "url", name="uq_attachment_item_url"),
    )

    item: Mapped["Item"] = relationship("Item", back_populates="attachments")


class NotificationSetting(Base):
    __tablename__ = "notification_settings"

    type: Mapped[str] = mapped_column(String(64), primary_key=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ntfy_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ntfy_topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
