"""merge_blob_storage_heads

Revision ID: b7c4d2ef8a11
Revises: a3f9b21d7c4e, 8f9d2e7ac1b4
Create Date: 2026-05-05 09:15:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "b7c4d2ef8a11"
down_revision: Union[str, Sequence[str], None] = (
    "a3f9b21d7c4e",
    "8f9d2e7ac1b4",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
