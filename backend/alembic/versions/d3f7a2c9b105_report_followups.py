"""report followups

Revision ID: d3f7a2c9b105
Revises: c4d8e1a7f203
Create Date: 2026-10-25 21:10:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d3f7a2c9b105"
down_revision = "c4d8e1a7f203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_followups",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("report_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer_json", sa.JSON(), nullable=False),
        sa.Column("citations_json", sa.JSON(), nullable=False),
        sa.Column("validation_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="complete"),
        sa.Column("model_provider", sa.String(length=60), nullable=False, server_default="fallback"),
        sa.Column(
            "model_name", sa.String(length=100), nullable=False, server_default="degraded-template-v1"
        ),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["ai_reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_followup_report", "report_followups", ["report_id", "seq"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_followup_report", table_name="report_followups")
    op.drop_table("report_followups")
