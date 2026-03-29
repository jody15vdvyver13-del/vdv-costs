"""add submitter_phone to cost_entries

Revision ID: a3f9c21d4e87
Revises: f12e6e61c1b2
Create Date: 2026-03-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a3f9c21d4e87"
down_revision: Union[str, Sequence[str], None] = "f12e6e61c1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cost_entries",
        sa.Column("submitter_phone", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cost_entries", "submitter_phone")
