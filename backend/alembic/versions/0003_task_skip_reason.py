"""Persist review-task skip reasons."""

from alembic import op
import sqlalchemy as sa

revision = "0003_task_skip_reason"
down_revision = "0002_accounts_learning"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("daily_review_tasks", sa.Column("skip_reason", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("daily_review_tasks", "skip_reason")
