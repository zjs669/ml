"""password reset tokens & refresh sessions

Revision ID: c4d8e1a7f203
Revises: b7c1d9e2a4f0
Create Date: 2026-10-25 18:40:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c4d8e1a7f203"
down_revision = "b7c1d9e2a4f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("requested_ip", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("idx_reset_user_created", "password_reset_tokens", ["user_id", "created_at"])
    op.create_index("idx_reset_expires", "password_reset_tokens", ["expires_at"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("family_id", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jti"),
    )
    op.create_index("idx_refresh_user", "refresh_tokens", ["user_id"])
    op.create_index("idx_refresh_family", "refresh_tokens", ["family_id"])


def downgrade() -> None:
    op.drop_index("idx_refresh_family", table_name="refresh_tokens")
    op.drop_index("idx_refresh_user", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("idx_reset_expires", table_name="password_reset_tokens")
    op.drop_index("idx_reset_user_created", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
