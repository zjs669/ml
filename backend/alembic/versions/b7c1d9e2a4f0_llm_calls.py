"""llm call ledger

Revision ID: b7c1d9e2a4f0
Revises: 36ef0bbc152f
Create Date: 2026-10-24 22:10:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b7c1d9e2a4f0"
down_revision = "36ef0bbc152f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("chart_id", sa.BigInteger(), nullable=True),
        sa.Column("report_id", sa.BigInteger(), nullable=True),
        sa.Column("task", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("skill_key", sa.String(length=120), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_estimate", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("meta_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["chart_id"], ["chart_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["report_id"], ["ai_reports.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_llm_created", "llm_calls", ["created_at"], unique=False)
    op.create_index("idx_llm_user_created", "llm_calls", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_llm_user_created", table_name="llm_calls")
    op.drop_index("idx_llm_created", table_name="llm_calls")
    op.drop_table("llm_calls")
