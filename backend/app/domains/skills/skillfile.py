"""SKILL.md 加载器：每次 AI 调用前先读的「必读技能」。

和另外两个概念区分：

| 概念 | 位置 | 作用 |
|---|---|---|
| 任务包 | `app/domains/skills/packages/*.json` | 决定用哪段 prompt 模板、检索哪些主题 |
| 知识库 | MySQL `knowledge_chunks`（源 `docs/知识源/`） | 可引用的古籍片段，必须带 chunk_id |
| **技能文件** | `backend/skills/**/*.md` | 做事顺序与自查点，**每次注入**，不能当引用 |

加载规则（写死，不靠调用方自觉）：

1. 全局 `skills/SKILL.md` 与 `skills/<domain>/SKILL.md` 的 `always` 恒为 True；
2. 其余卡片要求 `status: approved` 且触发词命中，按「命中数 → priority」排序；
3. `_draft/` 目录不递归、不加载；跨 domain 不加载；
4. 单文件按 `max_chars` 截断，整段按 `budget` 截断（默认 4000 字符）。

缓存按目录内所有 `.md` 的 mtime 做指纹，改文件后自动失效；测试可显式 `reload()`。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import BACKEND_DIR

SKILLS_DIR = BACKEND_DIR / "skills"
GLOBAL_FILE = "SKILL.md"
DEFAULT_BUDGET = 4000
DEFAULT_MAX_CHARS = 2500

#: 外部技能包（如 taibu）的 interpretation/<体系>.md 按文件名映射到 domain
EXTERNAL_TRIGGERS: dict[str, tuple[str, ...]] = {
    "bazi": ("八字", "四柱", "日主", "十神", "大运", "流年", "命盘"),
    "ziwei": ("紫微", "宫位", "四化", "大限", "小限", "流年"),
    "liuyao": ("六爻", "卦", "世应", "动爻", "用神"),
    "qimen": ("奇门", "九宫", "八门", "值符", "值使"),
}

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_CACHE: dict[tuple[int, int, int], tuple["SkillDoc", ...]] = {}


@dataclass(frozen=True)
class SkillDoc:
    id: str
    domain: str
    title: str
    body: str
    always: bool
    triggers: tuple[str, ...]
    priority: int
    max_chars: int
    status: str
    version: str
    source: str
    path: str
    kind: str = "card"

    def render(self) -> str:
        text = self.body.strip()
        if len(text) > self.max_chars:
            text = text[: self.max_chars].rstrip() + "\n…[截断]"
        return f"### [{self.id}] {self.title}\n{text}"


@dataclass
class SkillBlock:
    text: str = ""
    ids: list[str] = field(default_factory=list)


def parse_front_matter(raw: str) -> tuple[dict[str, Any], str]:
    """极简 YAML front-matter：标量、行内数组、短横线数组。"""
    match = _FRONT_MATTER.match(raw)
    if not match:
        return {}, raw
    meta: dict[str, Any] = {}
    current: str | None = None
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and current:
            meta.setdefault(current, [])
            if isinstance(meta[current], list):
                meta[current].append(_scalar(stripped[2:]))
            continue
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key, value = key.strip(), value.strip()
        if value:
            meta[key] = _scalar(value)
            current = None
        else:
            meta[key] = []
            current = key
    return meta, raw[match.end() :]


def _scalar(text: str) -> Any:
    value = text.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [item.strip().strip("'\"") for item in inner.split(",") if item.strip()]
    plain = value.strip("'\"")
    if plain.isdigit() and not (len(plain) > 1 and plain.startswith("0")):
        return int(plain)
    if plain.lower() in ("true", "false"):
        return plain.lower() == "true"
    return plain


def _as_tuple(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value if str(item).strip())


def _load_file(
    path: Path, *, default_domain: str, force_always: bool = False, kind: str = "card"
) -> SkillDoc | None:
    meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
    status = str(meta.get("status") or "draft")
    if status != "approved":
        return None
    domain = str(meta.get("domain") or default_domain)
    always = True if force_always else bool(meta.get("always", False))
    return SkillDoc(
        id=str(meta.get("id") or path.stem),
        domain=domain,
        title=str(meta.get("title") or path.stem),
        body=body,
        always=always,
        triggers=_as_tuple(meta.get("triggers")),
        priority=int(meta.get("priority") or 0),
        max_chars=int(meta.get("max_chars") or DEFAULT_MAX_CHARS),
        status=status,
        version=str(meta.get("version") or ""),
        source=str(meta.get("source") or ""),
        path=_display_path(path),
        kind=kind,
    )


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(SKILLS_DIR)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _external_roots() -> list[Path]:
    """外部技能根目录（由 SKILLS_EXTRA_DIRS 配置，逗号/分号分隔）。"""
    from app.core.config import settings

    raw = (settings.skills_extra_dirs or "").replace(";", ",").replace("\n", ",")
    roots = [Path(item.strip()) for item in raw.split(",") if item.strip()]
    return [root for root in roots if root.is_dir()]


def _read_title(path: Path, body: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def _external_docs() -> list[SkillDoc]:
    """加载外部技能包。

    支持两种形态：
    - `<root>/SKILL.md`（或 `<root>/<pack>/SKILL.md`）：包说明，默认不强制注入；
    - `<root>/interpretation/<domain>.md`：按文件名映射到 bazi/ziwei/liuyao/qimen，
      作为辅助卡片按触发词注入。

    外部包不受本站 `status` 约束（对方不用这套字段），但属于显式配置的路径：
    不配置就不会被读到，也不会被复制进仓库。
    """
    docs: list[SkillDoc] = []
    for root in _external_roots():
        packs = [root] if (root / GLOBAL_FILE).is_file() else [
            child for child in root.iterdir() if (child / GLOBAL_FILE).is_file()
        ]
        for pack in packs:
            main = pack / GLOBAL_FILE
            meta, body = parse_front_matter(main.read_text(encoding="utf-8"))
            pack_id = str(meta.get("id") or meta.get("name") or pack.name)
            docs.append(
                SkillDoc(
                    id=pack_id,
                    domain=str(meta.get("domain") or "common"),
                    title=str(meta.get("title") or _read_title(main, body)),
                    body=body,
                    always=False,
                    triggers=_as_tuple(meta.get("triggers")) or ("排盘", "起卦", "命盘"),
                    priority=int(meta.get("priority") or 5),
                    max_chars=int(meta.get("max_chars") or 1200),
                    status="approved",
                    version=str(meta.get("version") or ""),
                    source=f"external:{pack}",
                    path=_display_path(main),
                    kind="external",
                )
            )
            interp = pack / "interpretation"
            if not interp.is_dir():
                continue
            for path in sorted(interp.glob("*.md")):
                domain = path.stem
                if domain not in EXTERNAL_TRIGGERS:
                    continue
                raw = path.read_text(encoding="utf-8")
                _, card_body = parse_front_matter(raw)
                docs.append(
                    SkillDoc(
                        id=f"{pack_id}.interpretation.{domain}",
                        domain=domain,
                        title=f"{pack_id} · {domain} 解读指引",
                        body=card_body,
                        always=False,
                        triggers=EXTERNAL_TRIGGERS[domain],
                        priority=20,
                        max_chars=1600,
                        status="approved",
                        version="",
                        source=f"external:{path}",
                        path=_display_path(path),
                        kind="external_card",
                    )
                )
    return docs


def _signature() -> tuple[int, int, int]:
    files: list[Path] = []
    if SKILLS_DIR.is_dir():
        files.extend(p for p in SKILLS_DIR.rglob("*.md") if "_draft" not in p.parts)
    for root in _external_roots():
        files.extend(root.rglob("interpretation/*.md"))
        main = root / GLOBAL_FILE
        if main.is_file():
            files.append(main)
    if not files:
        return (0, 0, 0)
    return (len(files), max((p.stat().st_mtime_ns for p in files), default=0), len(_external_roots()))


def _docs() -> tuple[SkillDoc, ...]:
    key = _signature()
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    docs: list[SkillDoc] = []
    global_path = SKILLS_DIR / GLOBAL_FILE
    if global_path.is_file():
        doc = _load_file(global_path, default_domain="common", force_always=True, kind="global")
        if doc:
            docs.append(doc)
    for domain_dir in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()):
        if domain_dir.name.startswith("_"):
            continue
        main = domain_dir / GLOBAL_FILE
        if main.is_file():
            doc = _load_file(
                main, default_domain=domain_dir.name, force_always=True, kind="domain"
            )
            if doc:
                docs.append(doc)
        cards_dir = domain_dir / "cards"
        if cards_dir.is_dir():
            for path in sorted(cards_dir.glob("*.md")):
                doc = _load_file(path, default_domain=domain_dir.name)
                if doc:
                    docs.append(doc)
    result = tuple(docs + _external_docs())
    _CACHE.clear()
    _CACHE[key] = result
    return result


def reload() -> None:
    _CACHE.clear()


def available_ids(domain: str) -> list[str]:
    return [doc.id for doc in _docs() if doc.domain in ("common", domain)]


def select(
    domain: str, *, text: str = "", budget: int = DEFAULT_BUDGET, profile: str = "product"
) -> list[SkillDoc]:
    """按预算挑选。

    `profile="product"`：全局 + 领域 SKILL.md 必读，卡片按触发词追加；
    `profile="bench"`：只读 `skills/bench/SKILL.md` + 同 domain 卡片。
    评测题问的是“哪年发生何事”，与产品“不做断语”的人设冲突；
    混用会让模型拒答/回避，测出来的是人设而不是判断力。
    """
    haystack = text or ""
    if profile == "bench":
        docs = [doc for doc in _docs() if doc.domain == "bench"]
        required = [doc for doc in docs if doc.always or doc.kind == "domain"]
        cards = [
            doc
            for doc in _docs()
            if doc.domain == domain and doc.kind == "card" and doc.status == "approved"
        ]
    else:
        docs = [doc for doc in _docs() if doc.domain in ("common", domain)]
        required = [doc for doc in docs if doc.kind in ("global", "domain")]
        cards = [doc for doc in docs if doc.kind == "card"]

    # 外部技能包：只取 interpretation/<domain>.md（包说明里是对方 CLI 用法，不能直接执行，也不该占预算）
    from app.core.config import settings

    external = [
        doc for doc in _docs() if doc.kind == "external_card" and doc.domain == domain
    ]
    if profile != "bench" and not settings.skills_external_in_product:
        external = []
    cards = [*cards, *external]

    optional: list[tuple[int, int, SkillDoc]] = []
    for doc in cards:
        hits = sum(1 for trigger in doc.triggers if trigger and trigger in haystack)
        if hits == 0 and not doc.always:
            continue
        optional.append((hits, doc.priority, doc))
    optional.sort(key=lambda item: (item[0], item[1]), reverse=True)

    chosen: list[SkillDoc] = []
    used = 0
    for doc in [*required, *(item[2] for item in optional)]:
        cost = len(doc.render())
        if used + cost > budget:
            continue
        chosen.append(doc)
        used += cost
    return chosen


def render(
    domain: str, *, text: str = "", budget: int = DEFAULT_BUDGET, profile: str = "product"
) -> SkillBlock:
    docs = select(domain, text=text, budget=budget, profile=profile)
    if not docs:
        return SkillBlock()
    required = [doc for doc in docs if doc.kind in ("global", "domain")]
    cards = [doc for doc in docs if doc.kind == "card"]
    external = [doc for doc in docs if doc.kind.startswith("external")]

    parts: list[str] = []
    if required:
        parts.append("【必读技能】以下顺序与自查点每次都要遵守。\n" + "\n\n".join(d.render() for d in required))
    if cards:
        parts.append(
            "【参考经验】按触发词命中的经验卡，只作组织叙述的提示。\n"
            "它们不是事实来源，也不得写进 citations。\n"
            + "\n\n".join(d.render() for d in cards)
        )
    if external:
        parts.append(
            "【外部技能包】以下来自外部项目，仅作方法参考；其中的吉凶断语与绝对化表述不得照搬，"
            "与本项目红线冲突时以本项目为准，也不得写进 citations。\n"
            + "\n\n".join(d.render() for d in external)
        )
    text_out = "\n\n".join(parts)
    if len(text_out) > budget:
        text_out = text_out[:budget].rstrip() + "\n…[截断]"
    return SkillBlock(text=text_out, ids=[doc.id for doc in docs])
