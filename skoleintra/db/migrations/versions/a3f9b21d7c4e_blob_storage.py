"""blob_storage_s3_metadata

Revision ID: c91f4a2e5b6d
Revises: 6020f3a7eaa5
Create Date: 2026-05-05 09:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c91f4a2e5b6d"
down_revision: Union[str, Sequence[str], None] = "6020f3a7eaa5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("attachments", "local_path", new_column_name="blob_key")
    op.add_column("attachments", sa.Column("content_type", sa.Text(), nullable=True))
    op.add_column(
        "attachments", sa.Column("size_bytes", sa.BigInteger(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("attachments", "size_bytes")
    op.drop_column("attachments", "content_type")
    op.alter_column("attachments", "blob_key", new_column_name="local_path")
