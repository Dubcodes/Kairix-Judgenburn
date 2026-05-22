"""add connectivity settings

Revision ID: 20260507_0002
Revises: 20260507_0001
Create Date: 2026-05-07
"""

from alembic import op


revision = "20260507_0002"
down_revision = "20260507_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE event_settings ADD COLUMN IF NOT EXISTS connectivity_config JSON DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE event_settings DROP COLUMN IF EXISTS connectivity_config")
