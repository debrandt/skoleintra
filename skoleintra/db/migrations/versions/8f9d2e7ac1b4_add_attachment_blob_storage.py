"""add_attachment_blob_storage

Revision ID: 8f9d2e7ac1b4
Revises: 6020f3a7eaa5
Create Date: 2026-04-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8f9d2e7ac1b4"
down_revision: Union[str, Sequence[str], None] = "6020f3a7eaa5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attachment_blobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("attachment_id", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("blob", sa.LargeBinary(), nullable=False),
        sa.Column(
            "downloaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["attachment_id"], ["attachments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attachment_id", name="uq_attachment_blob_attachment"),
    )
    op.create_index(
        "ix_attachment_blobs_downloaded_at",
        "attachment_blobs",
        ["downloaded_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_attachment_blobs_downloaded_at", table_name="attachment_blobs")
    op.drop_table("attachment_blobs")
