"""add name to jobs

Revision ID: b7d3e92a1f04
Revises: a3f9c21d4e87
Create Date: 2026-03-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7d3e92a1f04"
down_revision: Union[str, Sequence[str], None] = "a3f9c21d4e87"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("name", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("jobs", "name")
