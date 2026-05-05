"""photo_album_item_type_split

Revision ID: d8a4c6f1b2e0
Revises: b4c9d2e7f1a3
Create Date: 2026-05-05 11:55:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8a4c6f1b2e0"
down_revision: Union[str, Sequence[str], None] = "b4c9d2e7f1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE items SET type = 'photo_album' WHERE type = 'photo'")
    op.execute(
        """
        UPDATE notification_settings
        SET type = 'photo_album'
        WHERE type = 'photo'
        """
    )
    op.execute(
        """
        INSERT INTO notification_settings (type, email_enabled, ntfy_enabled, ntfy_topic)
        SELECT 'photo', email_enabled, ntfy_enabled, ntfy_topic
        FROM notification_settings
        WHERE type = 'photo_album'
          AND NOT EXISTS (
              SELECT 1 FROM notification_settings WHERE type = 'photo'
          )
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM notification_settings WHERE type = 'photo'")
    op.execute(
        """
        UPDATE notification_settings
        SET type = 'photo'
        WHERE type = 'photo_album'
        """
    )
    op.execute("UPDATE items SET type = 'photo' WHERE type = 'photo_album'")
