"""Restructure schema: remove Kaggle columns from patients, add category to lab_results,
enhance lab_references with clinical fields.

Revision ID: a3b4c5d6e7f8
Revises: 1724a233d021
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "a3b4c5d6e7f8"
down_revision = "1724a233d021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── patients: remove Kaggle-only columns ──────────────────────────────────
    op.drop_column("patients", "date_of_admission")
    op.drop_column("patients", "discharge_date")
    op.drop_column("patients", "kaggle_test_result")

    # ── lab_results: add category column ─────────────────────────────────────
    op.add_column(
        "lab_results",
        sa.Column(
            "category",
            sa.String(50),
            nullable=False,
            server_default="others",
        ),
    )

    # ── lab_references: add clinical enrichment columns ───────────────────────
    op.add_column(
        "lab_references",
        sa.Column("category", sa.String(50), nullable=False, server_default="others"),
    )
    op.add_column(
        "lab_references",
        sa.Column("unit", sa.String(50), nullable=True),
    )
    op.add_column(
        "lab_references",
        sa.Column("advice", sa.Text, nullable=True),
    )
    op.add_column(
        "lab_references",
        sa.Column("causes_high", sa.Text, nullable=True),
    )
    op.add_column(
        "lab_references",
        sa.Column("causes_low", sa.Text, nullable=True),
    )
    op.add_column(
        "lab_references",
        sa.Column("specialist_type", sa.String(100), nullable=True),
    )
    op.add_column(
        "lab_references",
        sa.Column("retesting_urgency", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    # ── lab_references: remove added columns ──────────────────────────────────
    for col in ("retesting_urgency", "specialist_type", "causes_low",
                "causes_high", "advice", "unit", "category"):
        op.drop_column("lab_references", col)

    # ── lab_results: remove category ─────────────────────────────────────────
    op.drop_column("lab_results", "category")

    # ── patients: restore Kaggle columns ─────────────────────────────────────
    op.add_column("patients", sa.Column("kaggle_test_result", sa.String(50), nullable=True))
    op.add_column("patients", sa.Column("discharge_date", sa.Date, nullable=True))
    op.add_column("patients", sa.Column("date_of_admission", sa.Date, nullable=True))
