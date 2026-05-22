"""baseline current schema

Revision ID: 20260507_0001
Revises:
Create Date: 2026-05-07
"""

from typing import Sequence, Union

revision: str = "20260507_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Baseline migration for the schema currently created by SQLAlchemy models.
    # Existing installs should be stamped to this revision before future
    # migrations start making structural changes.
    pass


def downgrade() -> None:
    pass
