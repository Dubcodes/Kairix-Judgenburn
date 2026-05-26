"""add public notices and scoring options

Revision ID: 20260527_0004
Revises: 20260525_0003
Create Date: 2026-05-27
"""

from alembic import op


revision = "20260527_0004"
down_revision = "20260525_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE event_settings ADD COLUMN IF NOT EXISTS queue_notice TEXT")
    op.execute("ALTER TABLE event_settings ADD COLUMN IF NOT EXISTS public_notice TEXT")
    op.execute(
        "ALTER TABLE event_settings ADD COLUMN IF NOT EXISTS score_aggregation_mode VARCHAR(40) DEFAULT 'sum_all_judges'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE event_settings DROP COLUMN IF EXISTS score_aggregation_mode")
    op.execute("ALTER TABLE event_settings DROP COLUMN IF EXISTS public_notice")
    op.execute("ALTER TABLE event_settings DROP COLUMN IF EXISTS queue_notice")
