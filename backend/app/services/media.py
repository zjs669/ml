"""图片存储：面相 / 手相的上传落盘与清理。

设计取舍：
- **不进数据库 BLOB**：图片放文件系统，库里只存 sha256 与相对路径。原因是
  MySQL 存大对象会让备份、迁移、按行读取都变慢，且无法用 CDN 直接分发。
- **按内容寻址**：文件名取 sha256 前两位做子目录、全哈希做文件名，天然去重。
  同一张图重复上传不会占第二份空间。
- **剥 EXIF**：上传即重新编码，只保留像素。人脸照片的 GPS、设备型号、
  拍摄时间都属于不该留存的元数据。
- **MIME 白名单**：只接受 jpeg / png / webp，不靠扩展名判断。

本模块不接触数据库，也不接触模型 —— 只做「字节 → 安全文件」这一件事。
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings

#: 只接受这三种；heic/gif/bmp 一律拒绝（gif 可能是动图，人脸分析无意义）
ALLOWED_MIME: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

#: 图片尺寸上限（单边），超过直接拒绝而不是缩图 —— 缩图会悄悄改变分析对象
MAX_EDGE = 4096

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class MediaError(ValueError):
    """上传的图片不合法（格式、大小、尺寸、内容）。"""


@dataclass(frozen=True)
class StoredMedia:
    sha256: str
    mime: str
    size_bytes: int
    width: int
    height: int
    storage_key: str
    delete_after: datetime

    @property
    def path(self) -> Path:
        return settings.media_root_path / self.storage_key


def _extension(mime: str) -> str:
    normalized = (mime or "").strip().lower()
    if normalized not in ALLOWED_MIME:
        raise MediaError(f"不支持的图片格式「{mime}」，只接受 jpeg / png / webp")
    return ALLOWED_MIME[normalized]


def _strip_metadata(raw: bytes, mime: str) -> tuple[bytes, int, int]:
    """重新编码以剥离 EXIF / XMP / 缩略图，并返回像素尺寸。

    依赖 Pillow。缺库时**直接报错**而不是退回原图 —— 原图可能带 GPS，
    「装作用不了」比「悄悄保留元数据」更安全。
    """
    try:
        from PIL import Image
    except ModuleNotFoundError as exc:  # pragma: no cover - 正常安装环境不会触发
        raise MediaError(
            "图片处理需要 Pillow，请先执行 pip install Pillow（已列在 backend/requirements.txt）"
        ) from exc

    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            width, height = image.size
            if width > MAX_EDGE or height > MAX_EDGE:
                raise MediaError(f"图片尺寸 {width}x{height} 超过上限 {MAX_EDGE}x{MAX_EDGE}")
            # 统一转 RGB / RGBA，丢弃所有附加块（EXIF、GPS、XMP、缩略图）
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")
            buffer = io.BytesIO()
            fmt = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}[_extension(mime)]
            save_kwargs: dict[str, object] = {"format": fmt}
            if fmt == "JPEG":
                save_kwargs.update({"quality": 92, "optimize": True})
            elif fmt == "PNG":
                save_kwargs.update({"optimize": True})
            image.save(buffer, **save_kwargs)
            return buffer.getvalue(), width, height
    except MediaError:
        raise
    except Exception as exc:  # Pillow 对损坏文件抛的异常类型很杂
        raise MediaError(f"图片无法解码：{exc.__class__.__name__}") from exc


def store(raw: bytes, mime: str) -> StoredMedia:
    """校验 → 剥元数据 → 按内容寻址落盘。"""
    if not raw:
        raise MediaError("图片内容为空")
    if len(raw) > settings.media_max_bytes:
        limit_mb = settings.media_max_bytes / (1024 * 1024)
        raise MediaError(f"图片超过 {limit_mb:.1f} MiB 上限")

    cleaned, width, height = _strip_metadata(raw, mime)
    digest = hashlib.sha256(cleaned).hexdigest()
    ext = _extension(mime)
    storage_key = f"{digest[:2]}/{digest}.{ext}"

    root = settings.media_root_path
    target = root / storage_key
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        # 先写临时文件再改名：避免并发上传同一张图时读到半截文件
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_bytes(cleaned)
        temp.replace(target)

    delete_after = datetime.now(timezone.utc) + timedelta(days=settings.media_retention_days)
    return StoredMedia(
        sha256=digest,
        mime=(mime or "").strip().lower(),
        size_bytes=len(cleaned),
        width=width,
        height=height,
        storage_key=storage_key,
        delete_after=delete_after,
    )


def resolve(storage_key: str) -> Path:
    """把 storage_key 还原成路径，并拒绝任何越界路径（防目录穿越）。"""
    if not storage_key or ".." in storage_key or storage_key[0] in ("/", "\\"):
        raise MediaError(f"非法的 storage_key：{storage_key}")
    root = settings.media_root_path.resolve()
    candidate = (root / storage_key).resolve()
    if not str(candidate).startswith(str(root)):
        raise MediaError(f"storage_key 越出媒体目录：{storage_key}")
    return candidate


def is_valid_sha256(value: str) -> bool:
    return bool(_SHA256_RE.match(value or ""))


def purge_expired(now: datetime | None = None) -> list[str]:
    """删除超过留存期的文件，返回被删的 storage_key 列表。

    只删文件，不动数据库 —— 数据库行的清理由调用方负责，避免这里
    出现「文件没了但记录还在」的隐式依赖。
    """
    moment = now or datetime.now(timezone.utc)
    root = settings.media_root_path
    if not root.exists():
        return []
    removed: list[str] = []
    cutoff = moment.timestamp() - settings.media_retention_days * 86400
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.stat().st_mtime > cutoff:
            continue
        removed.append(str(path.relative_to(root)).replace("\\", "/"))
        path.unlink(missing_ok=True)
    return removed
