"""child_group_identity

Revision ID: 7b2c4d1e9f0a
Revises: c91f4a2e5b6d
Create Date: 2026-05-05 10:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b2c4d1e9f0a"
down_revision: Union[str, Sequence[str], None] = "c91f4a2e5b6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "children", sa.Column("source_id", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "children",
        sa.Column("is_present", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.drop_constraint("uq_child_name_hostname", "children", type_="unique")
    op.create_unique_constraint(
        "uq_child_source_hostname",
        "children",
        ["school_hostname", "source_id"],
    )

    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("school_hostname", sa.String(length=255), nullable=False),
        sa.Column(
            "is_present",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "school_hostname",
            "source_id",
            name="uq_group_source_hostname",
        ),
    )


def downgrade() -> None:
    op.drop_table("groups")
    op.drop_constraint("uq_child_source_hostname", "children", type_="unique")
    op.create_unique_constraint(
        "uq_child_name_hostname",
        "children",
        ["name", "school_hostname"],
    )
    op.drop_column("children", "is_present")
    op.drop_column("children", "source_id")
