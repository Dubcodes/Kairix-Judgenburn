"""add delay presets

Revision ID: 20260525_0003
Revises: 20260507_0002
Create Date: 2026-05-25
"""

from alembic import op


revision = "20260525_0003"
down_revision = "20260507_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE event_settings ADD COLUMN IF NOT EXISTS delay_presets JSON DEFAULT '[]'")


def downgrade() -> None:
    op.execute("ALTER TABLE event_settings DROP COLUMN IF EXISTS delay_presets")
