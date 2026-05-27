"""add public display configuration

Revision ID: 20260527_0005
Revises: 20260527_0004
Create Date: 2026-05-27
"""

from alembic import op


revision = "20260527_0005"
down_revision = "20260527_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE event_settings ADD COLUMN IF NOT EXISTS public_display_config JSON DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE event_settings DROP COLUMN IF EXISTS public_display_config")
