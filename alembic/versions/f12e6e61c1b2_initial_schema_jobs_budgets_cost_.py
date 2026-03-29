"""initial schema: jobs budgets cost_entries approved_vendors exceptions

Revision ID: f12e6e61c1b2
Revises:
Create Date: 2026-03-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f12e6e61c1b2"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN CREATE TYPE job_status AS ENUM ('active', 'completed', 'cancelled'); EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE category_code AS ENUM ("
        "'COG-01', 'COG-02', 'COG-03', 'COG-04',"
        "'COG-05', 'COG-06', 'COG-07', 'COG-08'); EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE cost_entry_status AS ENUM ('pending', 'posted', 'exception'); EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE vendor_status AS ENUM ('approved', 'suspended'); EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("reference", sa.String(20), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("contract_value", sa.Numeric(14, 2), nullable=True),
        sa.Column(
            "status",
            sa.Enum("active", "completed", "cancelled", name="job_status", create_type=False),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("reference", name="uq_jobs_reference"),
        sa.CheckConstraint(
            r"reference ~ '^VDV-JOB-\d{4}-\d{3}$'",
            name="ck_jobs_reference_format",
        ),
    )

    op.create_table(
        "budgets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "category_code",
            sa.Enum(
                "COG-01", "COG-02", "COG-03", "COG-04",
                "COG-05", "COG-06", "COG-07", "COG-08",
                name="category_code",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("budgeted_amount", sa.Numeric(14, 2), nullable=False),
        sa.UniqueConstraint("job_id", "category_code", name="uq_budgets_job_category"),
    )

    op.create_table(
        "approved_vendors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "status",
            sa.Enum("approved", "suspended", name="vendor_status", create_type=False),
            nullable=False,
            server_default="approved",
        ),
        sa.UniqueConstraint("name", name="uq_approved_vendors_name"),
    )

    op.create_table(
        "cost_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("supplier", sa.String(200), nullable=False),
        sa.Column("date", sa.String(10), nullable=True),
        sa.Column("amount_excl_vat", sa.Numeric(14, 2), nullable=True),
        sa.Column("amount_incl_vat", sa.Numeric(14, 2), nullable=True),
        sa.Column(
            "category_code",
            sa.Enum(
                "COG-01", "COG-02", "COG-03", "COG-04",
                "COG-05", "COG-06", "COG-07", "COG-08",
                name="category_code",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("slip_image_url", sa.String(1000), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "posted", "exception",
                name="cost_entry_status",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "exceptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "cost_entry_id",
            sa.Integer(),
            sa.ForeignKey("cost_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("exception_type", sa.String(100), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("exceptions")
    op.drop_table("cost_entries")
    op.drop_table("approved_vendors")
    op.drop_table("budgets")
    op.drop_table("jobs")
    op.execute("DROP TYPE IF EXISTS cost_entry_status")
    op.execute("DROP TYPE IF EXISTS vendor_status")
    op.execute("DROP TYPE IF EXISTS category_code")
    op.execute("DROP TYPE IF EXISTS job_status")
