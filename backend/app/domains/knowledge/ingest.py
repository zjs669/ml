"""知识库入库：Markdown → knowledge_sources / knowledge_chunks。

文件格式（`docs/知识源/*.md`）：

    ---
    title: 三命通会
    author: 万民英（明）
    edition: 文渊阁四库全书本（公版）
    license_status: public_domain
    source_url: https://zh.wikisource.org/wiki/三命通會
    ---

    ## 藏干
    @location: 卷一·论天干地支
    正文……

规则：
- `content_hash` 唯一，重复入库不会产生重复片段；
- 新片段一律 `pending`，必须经 `python -m scripts.admin approve` 审核后才可被检索；
- `license_status` 缺失直接拒绝整个文件——来源不明的文本不允许进库。
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import KnowledgeChunk, KnowledgeSource

FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.S)
SECTION = re.compile(r"^##\s+(.+?)\s*$", re.M)
LOCATION = re.compile(r"^@location:\s*(.+)$", re.M)
ALLOWED_LICENSE = {
    "public_domain",
    "public_domain_paraphrase",
    "self_written",
    "cc_by",
    "cc_by_sa",
    "licensed",
}


@dataclass
class ParsedChunk:
    topic: str
    content: str
    location: str | None
    content_hash: str


@dataclass
class ParsedSource:
    title: str
    author: str | None
    edition: str | None
    license_status: str
    source_url: str | None
    chunks: list[ParsedChunk]


def _parse_front_matter(text: str, path: Path) -> tuple[dict[str, str], str]:
    match = FRONT_MATTER.match(text)
    if not match:
        raise ValueError(f"{path.name}: 缺少 front matter（--- 元信息 ---）")
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, match.group(2)


def parse_file(path: Path) -> ParsedSource:
    meta, body = _parse_front_matter(path.read_text(encoding="utf-8"), path)
    for required in ("title", "license_status"):
        if not meta.get(required):
            raise ValueError(f"{path.name}: 缺少必填字段 {required}")
    license_status = meta["license_status"]
    if license_status not in ALLOWED_LICENSE:
        raise ValueError(f"{path.name}: license_status={license_status} 不在允许列表内")

    chunks: list[ParsedChunk] = []
    matches = list(SECTION.finditer(body))
    for index, match in enumerate(matches):
        topic = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        raw = body[start:end].strip()
        location_match = LOCATION.search(raw)
        location = location_match.group(1).strip() if location_match else None
        content = LOCATION.sub("", raw).strip()
        if not content:
            continue
        digest = hashlib.sha256(
            f"{meta['title']}|{topic}|{content}".encode("utf-8")
        ).hexdigest()
        chunks.append(
            ParsedChunk(topic=topic, content=content, location=location, content_hash=digest)
        )
    if not chunks:
        raise ValueError(f"{path.name}: 未解析到任何 ## 片段")
    return ParsedSource(
        title=meta["title"],
        author=meta.get("author"),
        edition=meta.get("edition"),
        license_status=license_status,
        source_url=meta.get("source_url"),
        chunks=chunks,
    )


def _upsert_source(session: Session, parsed: ParsedSource) -> KnowledgeSource:
    source = session.scalar(select(KnowledgeSource).where(KnowledgeSource.title == parsed.title))
    if source is None:
        source = KnowledgeSource(
            title=parsed.title,
            author=parsed.author,
            edition=parsed.edition,
            license_status=parsed.license_status,
            source_url=parsed.source_url,
            status="active",
        )
        session.add(source)
        session.flush()
    else:
        source.author = parsed.author or source.author
        source.edition = parsed.edition or source.edition
        source.license_status = parsed.license_status
        source.source_url = parsed.source_url or source.source_url
        session.add(source)
    return source


def ingest_directory(
    session: Session,
    directory: Path,
    *,
    domain: str = "bazi",
    approve: bool = False,
) -> dict[str, int]:
    stats = {"sources": 0, "added": 0, "skipped": 0}
    for path in sorted(directory.glob("*.md")):
        parsed = parse_file(path)
        source = _upsert_source(session, parsed)
        stats["sources"] += 1
        for chunk in parsed.chunks:
            exists = session.scalar(
                select(KnowledgeChunk).where(KnowledgeChunk.content_hash == chunk.content_hash)
            )
            if exists is not None:
                stats["skipped"] += 1
                continue
            session.add(
                KnowledgeChunk(
                    source_id=source.id,
                    domain=domain,
                    topic=chunk.topic,
                    content=chunk.content,
                    citation_label=f"{parsed.title}·{chunk.topic}",
                    location=chunk.location,
                    keywords=chunk.topic,
                    content_hash=chunk.content_hash,
                    approval_status="approved" if approve else "pending",
                )
            )
            stats["added"] += 1
        session.flush()
    session.commit()
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="知识库入库")
    parser.add_argument("--dir", default="docs/知识源", help="Markdown 目录")
    parser.add_argument("--domain", default="bazi")
    parser.add_argument("--approve", action="store_true", help="入库即审核通过（仅本地开发使用）")
    args = parser.parse_args(argv)

    directory = Path(args.dir)
    if not directory.is_absolute():
        directory = Path(__file__).resolve().parents[4] / args.dir
    if not directory.is_dir():
        print(f"目录不存在: {directory}", file=sys.stderr)
        return 2

    with SessionLocal() as session:
        stats = ingest_directory(session, directory, domain=args.domain, approve=args.approve)
    print(
        f"知识源 {stats['sources']} 个，新增片段 {stats['added']}，已存在跳过 {stats['skipped']}"
        f"（approval={'approved' if args.approve else 'pending'}）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
