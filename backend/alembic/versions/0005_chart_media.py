"""chart media（面相 / 手相图片元信息）

Revision ID: e6b2d4a8c930

文件名：<序号>_<描述>.py。序号只为阅读方便，**Alembic 不读文件名** ——
它读本文件里的 `revision` 值（undefined），数据库 alembic_version 表存的也是这个值。
所以重命名文件是安全的，改 `revision` 值才危险。
Revises: d3f7a2c9b105
Create Date: 2026-10-25 23:50:00.000000

为什么单独建表而不是塞进 chart_records.chart_json：
- 单张 5 MiB 的 base64 会让每行记录膨胀 6.7 MiB，列表查询与备份都被拖垮；
- 图片有独立的留存期（比命盘短），混在一起无法单独清理；
- 图片需要按 owner 去重（同一张图重复上传不占第二份空间），需要独立索引。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e6b2d4a8c930"
down_revision = "d3f7a2c9b105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chart_media",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("chart_id", sa.BigInteger(), nullable=True),
        sa.Column("media_kind", sa.String(length=20), nullable=False),
        sa.Column("mime", sa.String(length=40), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=120), nullable=False),
        sa.Column("delete_after", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chart_id"], ["chart_records.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_media_owner_created", "chart_media", ["owner_user_id", "created_at"], unique=False
    )
    op.create_index("idx_media_chart", "chart_media", ["chart_id"], unique=False)
    op.create_index("idx_media_expire", "chart_media", ["delete_after"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_media_expire", table_name="chart_media")
    op.drop_index("idx_media_chart", table_name="chart_media")
    op.drop_index("idx_media_owner_created", table_name="chart_media")
    op.drop_table("chart_media")
