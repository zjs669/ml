"""面相 / 手相服务层测试。

重点不是「模型输出对不对」（那是模型的事），而是四条边界：
1. 图片必须先剥元数据再落盘，且按内容寻址去重；
2. 未配置视觉模型时必须直接拒绝，不回落到文本模型；
3. 模型不可用时额度必须全额退回，不能扣了钱却没结果；
4. `chart_facts` 只放用户输入与媒体元信息，**不放模型输出**。
"""

from __future__ import annotations

import io
import uuid

import pytest
from PIL import Image

from app.core.config import settings
from app.domains.vision import prompts, service as vision_service
from app.services import media


def _jpeg(color: tuple[int, int, int] = (200, 180, 160), size: tuple[int, int] = (64, 64)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG")
    return buffer.getvalue()


# ---- media.store ----


def test_store_strips_metadata_and_reencodes(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "media_root", str(tmp_path), raising=False)
    stored = media.store(_jpeg(), "image/jpeg")
    assert stored.path.exists()
    assert stored.width == 64 and stored.height == 64
    assert stored.sha256 == __import__("hashlib").sha256(stored.path.read_bytes()).hexdigest()
    # 重编码后的体积通常小于原图，且不再含 EXIF 段
    raw = stored.path.read_bytes()
    assert b"Exif" not in raw


def test_store_is_content_addressed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "media_root", str(tmp_path), raising=False)
    first = media.store(_jpeg(), "image/jpeg")
    second = media.store(_jpeg(), "image/jpeg")
    assert first.sha256 == second.sha256
    assert first.storage_key == second.storage_key
    files = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert len(files) == 1


def test_store_rejects_unsupported_mime(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "media_root", str(tmp_path), raising=False)
    with pytest.raises(media.MediaError):
        media.store(_jpeg(), "image/gif")


def test_store_rejects_oversized(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "media_root", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "media_max_bytes", 100, raising=False)
    with pytest.raises(media.MediaError):
        media.store(_jpeg(), "image/jpeg")


def test_store_rejects_garbage_bytes(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "media_root", str(tmp_path), raising=False)
    with pytest.raises(media.MediaError):
        media.store(b"not-an-image-at-all", "image/jpeg")


def test_store_rejects_oversized_dimensions(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "media_root", str(tmp_path), raising=False)
    with pytest.raises(media.MediaError):
        media.store(_jpeg(size=(media.MAX_EDGE + 1, 16)), "image/jpeg")


def test_resolve_rejects_traversal(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "media_root", str(tmp_path), raising=False)
    for bad in ("../etc/passwd", "/abs/path", ""):
        with pytest.raises(media.MediaError):
            media.resolve(bad)


def test_purge_expired_removes_old_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "media_root", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "media_retention_days", 0, raising=False)
    stored = media.store(_jpeg(), "image/jpeg")
    removed = media.purge_expired()
    assert stored.storage_key in removed
    assert not stored.path.exists()


# ---- prompts ----


def test_face_types_are_complete() -> None:
    ids = [item.id for item in prompts.FACE_TYPES]
    assert "full" in ids and len(ids) == len(set(ids))
    for item in prompts.FACE_TYPES:
        assert item.name and item.description and item.focus


def test_palm_types_are_complete() -> None:
    ids = [item.id for item in prompts.PALM_TYPES]
    assert "full" in ids and len(ids) == len(set(ids))


def test_prompts_forbid_inference() -> None:
    """提示词必须显式禁止推断性格/健康/命运，否则模型一定会写。"""
    system = prompts.build_face_system_prompt("full")
    for banned in ("不推断性格", "健康", "命运", "uncertainties"):
        assert banned in system, f"提示词缺少约束：{banned}"


def test_prompts_reject_unknown_type() -> None:
    with pytest.raises(ValueError):
        prompts.build_face_system_prompt("no-such-type")
    with pytest.raises(ValueError):
        prompts.build_palm_user_prompt("no-such-type", "left", None)


def test_prompt_includes_question_when_given() -> None:
    with_q = prompts.build_face_user_prompt("full", "我想了解事业方向")
    without = prompts.build_face_user_prompt("full", None)
    assert "事业方向" in with_q
    assert "补充问题" not in without


def test_titles_are_domain_specific() -> None:
    assert "面相" in prompts.generate_face_title("full")
    assert "手相" in prompts.generate_palm_title("lines", "right")
    assert "右手" in prompts.generate_palm_title("lines", "right")


# ---- service ----


def test_rejects_when_vision_not_configured(monkeypatch) -> None:
    """未配置视觉模型时必须直接拒绝，不能悄悄回落到文本模型。"""
    monkeypatch.setattr(settings, "llm_vision_model", "", raising=False)
    monkeypatch.setattr(settings, "llm_vision_api_key", "", raising=False)
    with pytest.raises(vision_service.VisionNotConfigured):
        vision_service._provider()


def test_unknown_kind_rejected() -> None:
    with pytest.raises(Exception):
        vision_service.analyze(
            None,  # type: ignore[arg-type]
            user_id=1,
            kind="nose",
            raw=b"x",
            mime="image/jpeg",
            analysis_type="full",
            idempotency_key=uuid.uuid4().hex,
        )


def test_facts_exclude_model_output() -> None:
    """`chart_facts` 只能是用户输入 + 媒体元信息，模型输出不许进来。"""
    row = type("Row", (), {})()
    row.sha256 = "a" * 64
    row.mime = "image/jpeg"
    row.width = 100
    row.height = 120
    row.size_bytes = 2048
    facts = vision_service._facts("face", row, "full", None, "想问事业", True)
    assert set(facts) == {"media", "analysis_type", "question"}
    assert "observations" not in facts
    assert "interpretations" not in facts


def test_facts_drop_question_when_not_stored() -> None:
    row = type("Row", (), {})()
    row.sha256 = "b" * 64
    row.mime = "image/png"
    row.width = 10
    row.height = 10
    row.size_bytes = 100
    facts = vision_service._facts("palm", row, "lines", "left", "秘密问题", False)
    assert "question" not in facts
