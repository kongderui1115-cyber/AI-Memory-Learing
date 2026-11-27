"""Persist Notion page archive state and reconciliation cursor."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_notion_lifecycle"
down_revision = "0005_guided_setup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chapters", sa.Column("notion_archived_at", sa.DateTime(timezone=True)))
    op.add_column("notion_data_sources", sa.Column("lifecycle_cursor", sa.String(128)))
    op.add_column(
        "workspace_profiles",
        sa.Column("review_preferences", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("workspace_profiles", "review_preferences")
    op.drop_column("notion_data_sources", "lifecycle_cursor")
    op.drop_column("chapters", "notion_archived_at")
