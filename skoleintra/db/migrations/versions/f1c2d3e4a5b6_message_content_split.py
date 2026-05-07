"""Persist split Message content fields.

Revision ID: f1c2d3e4a5b6
Revises: d8a4c6f1b2e0
Create Date: 2026-05-07 11:55:00.000000
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f1c2d3e4a5b6"
down_revision = "d8a4c6f1b2e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("message_body_html", sa.Text(), nullable=True))
    op.add_column(
        "items", sa.Column("message_quoted_body_html", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("items", "message_quoted_body_html")
    op.drop_column("items", "message_body_html")
