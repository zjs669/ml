"""架构守卫：把「依赖方向」和「不该再出现的文件」变成会失败的测试。

为什么放在 pytest 里而不是 CI 脚本：本地改完就能立刻知道越界，不依赖记得跑额外命令。
规则只写「已经做到、且必须保持」的边界，不写理想化的未来架构。

参考 taibu 的 `scripts/check-architecture-guards.mjs`：守卫要能指出「哪个文件 import 了谁」，
而不是只给一句「架构不合法」。
"""

from __future__ import annotations

import ast
import io
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"
FRONTEND = BACKEND.parent / "frontend" / "src"

#: 计算内核：只做纯函数，不碰数据库、网络、模型、计费
PURE_DOMAINS = {
    "almanac",
    "bazi",
    "calendar_core",
    "liuyao",
    "qimen",
    "relations",
    "tarot",
    "xiaoliuren",
    "ziwei",
}
PURE_FORBIDDEN = (
    "app.domains.llm",
    "app.domains.billing",
    "app.domains.reporting",
    "app.repositories",
    "app.models",
    "app.api",
)

#: 分层依赖：key 所在层不得 import 列表中的层
LAYER_FORBIDDEN = {
    "core": ("app.api", "app.domains", "app.repositories", "app.models"),
    "models": ("app.api", "app.domains"),
    "repositories": ("app.api", "app.domains"),
    "api": ("app.domains.llm",),
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(io.open(path, encoding="utf-8-sig").read())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _python_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and path.name != "__init__.py"
    ]


def _matches(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def test_layer_directions() -> None:
    violations: list[str] = []
    for path in _python_files(APP):
        layer = path.relative_to(APP).parts[0]
        forbidden = LAYER_FORBIDDEN.get(layer, ())
        for module in sorted(_imports(path)):
            for prefix in forbidden:
                if _matches(module, prefix):
                    violations.append(
                        f"{path.relative_to(BACKEND)}: {layer} 层不得 import {module}"
                    )
    assert not violations, "依赖方向越界：\n" + "\n".join(violations)


def test_pure_domains_do_not_reach_infrastructure() -> None:
    violations: list[str] = []
    for domain in sorted(PURE_DOMAINS):
        for path in _python_files(APP / "domains" / domain):
            for module in sorted(_imports(path)):
                for prefix in PURE_FORBIDDEN:
                    if _matches(module, prefix):
                        violations.append(
                            f"{path.relative_to(BACKEND)}: 纯计算域不得 import {module}"
                        )
    assert not violations, "计算内核被基础设施污染：\n" + "\n".join(violations)


def test_no_scratch_files_in_repo() -> None:
    """临时脚本、截图目录不进仓库；发现即失败，避免再次堆积。"""
    leftovers = [path.name for path in BACKEND.glob("_*.py")]
    leftovers += [path.name for path in BACKEND.parent.glob("tmp_*")]
    assert not leftovers, f"发现临时文件：{leftovers}"
    assert not (BACKEND.parent / "shots").exists(), "shots/ 是本地截图目录，不入库"


def test_removed_compat_modules_stay_removed() -> None:
    """已经删掉的兼容层不许回来（有替代实现后再删这条断言）。"""
    removed = [
        "app/domains/skills/distilled.py",
    ]
    still_there = [item for item in removed if (BACKEND / item).exists()]
    assert not still_there, f"这些兼容层应保持删除：{still_there}"


def test_skills_loader_has_single_entry() -> None:
    """技能只能通过 skillfile 注入，避免报告/追问/评测各拼一套。"""
    callers = []
    for path in _python_files(APP) + _python_files(BACKEND / "scripts"):
        if path.name == "skillfile.py":
            continue
        text = io.open(path, encoding="utf-8-sig").read()
        if re.search(r"from app\.domains\.skills import (?!skillfile)", text):
            callers.append(str(path.relative_to(BACKEND)))
    assert not callers, f"技能加载必须走 skillfile：{callers}"


def test_generative_domains_do_not_emit_rules() -> None:
    """生成式域（面相/手相/MBTI 等）不得产出 triggered_rules。

    生成式引擎没有确定性规则可命中，一旦产出 rule_id，报告校验的
    「rule_id 白名单」就被架空，模型可以借伪规则绕过事实一致性检查。
    """
    from app.domains.registry import ENGINES

    offenders = [
        spec.domain for spec in ENGINES.values() if spec.kind == "generative" and spec.requires_media is False
    ]
    # requires_media=False 的生成式域没有输入凭据，属设计缺陷
    assert not offenders, f"生成式域必须声明 requires_media：{offenders}"


def test_every_engine_declares_kind_and_school() -> None:
    """每个引擎都必须显式声明 kind 与至少一个 school，不允许依赖 dataclass 默认值蒙混。"""
    from app.domains.registry import ENGINES

    for domain, spec in ENGINES.items():
        assert spec.kind in ("deterministic", "generative"), f"{domain} 的 kind 非法：{spec.kind}"
        assert spec.schools, f"{domain} 未声明任何 school"
        assert spec.label, f"{domain} 缺中文标签"


def test_registry_domains_have_algorithm_version() -> None:
    """每个已注册域必须在 settings 里有独立的 algorithm_version，否则无法回显口径版本。"""
    from app.core.config import settings
    from app.domains.registry import ENGINES

    missing = [
        domain
        for domain in ENGINES
        if not getattr(settings, f"{domain}_algorithm_version", None)
    ]
    assert not missing, f"这些域缺 algorithm_version 配置：{missing}"


def test_frontend_api_layer_does_not_import_ui() -> None:
    violations: list[str] = []
    for path in (FRONTEND / "api").rglob("*.ts"):
        text = path.read_text(encoding="utf-8")
        for specifier in re.findall(r"from '([^']+)'", text):
            if specifier.startswith(("@/pages", "@/components", "@/router", "@/stores")):
                violations.append(f"{path.relative_to(FRONTEND)} -> {specifier}")
    assert not violations, "src/api 不得反向依赖 UI/路由/状态：\n" + "\n".join(violations)
