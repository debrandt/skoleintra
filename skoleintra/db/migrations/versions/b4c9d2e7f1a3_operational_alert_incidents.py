"""operational_alert_incidents

Revision ID: b4c9d2e7f1a3
Revises: 7b2c4d1e9f0a
Create Date: 2026-05-05 10:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4c9d2e7f1a3"
down_revision: Union[str, Sequence[str], None] = "7b2c4d1e9f0a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operational_incidents",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("subsystem", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=255), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.String(length=255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("first_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_recovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("operational_incidents")
