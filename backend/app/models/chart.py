"""命盘、笔记、分享链接。所有查询必须带 owner 过滤（只在 repositories 里做）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import utcnow
from app.models.base import Base


class ChartRecord(Base):
    __tablename__ = "chart_records"
    __table_args__ = (
        Index("idx_chart_owner_created", "owner_user_id", "created_at"),
        Index("idx_chart_domain_created", "domain", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    domain: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    input_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    chart_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    convention_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(80), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, default="private", server_default="private"
    )
    delete_after: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class ChartNote(Base):
    __tablename__ = "chart_notes"
    __table_args__ = (Index("idx_note_chart", "chart_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chart_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chart_records.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class ShareLink(Base):
    """分享链接：只存 token 的 SHA-256，明文仅在创建时返回一次（文档 4.3）。"""

    __tablename__ = "share_links"
    __table_args__ = (Index("idx_share_chart", "chart_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chart_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chart_records.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    redact_level: Mapped[str] = mapped_column(String(20), nullable=False, default="basic")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ChartMedia(Base):
    """面相 / 手相上传的图片元信息。二进制落文件系统，库里只存哈希与路径。

    为什么不把图片塞进 `chart_records.chart_json`：
    - 单张 5 MiB 的 base64 会让每行记录膨胀 6.7 MiB，列表查询与备份都被拖垮；
    - 图片有独立的留存期（比命盘短），混在一起无法单独清理。

    为什么 `chart_id` 可空：先分析后保存是正常流程，分析时命盘还不存在。
    """

    __tablename__ = "chart_media"
    __table_args__ = (
        Index("idx_media_owner_created", "owner_user_id", "created_at"),
        Index("idx_media_chart", "chart_id"),
        Index("idx_media_expire", "delete_after"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    #: 未保存命盘时为空；保存后回填
    chart_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chart_records.id", ondelete="SET NULL"), nullable=True
    )
    #: face / palm
    media_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    mime: Mapped[str] = mapped_column(String(40), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    #: 内容哈希（已剥元数据后的字节），同时作为去重键
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    #: 相对 media_root 的路径，形如 "ab/abcd...ef.jpg"
    storage_key: Mapped[str] = mapped_column(String(120), nullable=False)
    delete_after: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
