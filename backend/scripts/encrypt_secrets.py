"""把 `.env` 里的第三方密钥就地改成密文（`enc:v1:...`）。

用法：
    python -m scripts.encrypt_secrets              # 加密 .env 里的默认项
    python -m scripts.encrypt_secrets --check      # 只检查，不改文件
    python -m scripts.encrypt_secrets --keys LLM_API_KEY,SMTP_PASSWORD

约定：
- 默认处理 `LLM_API_KEY` / `SMTP_PASSWORD`（这两项是程序要用、又不能哈希的）；
- 改文件前先备份成 `.env.bak`，写回保留注释与空行，只替换目标行的值；
- 打印一律用掩码与指纹，**绝不打印明文**；
- 已加密的行跳过，可反复执行。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from app.core.config import BACKEND_DIR
from app.core.secrets import PREFIX, encrypt_value, is_encrypted, mask

DEFAULT_KEYS = ("LLM_API_KEY", "SMTP_PASSWORD")
ENV_PATH = BACKEND_DIR / ".env"


def _split(line: str) -> tuple[str, str] | None:
    """把 `KEY=value` 拆成两部分；注释行与无等号行返回 None。"""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return None
    key, _, value = stripped.partition("=")
    return key.strip(), value.strip()


def _quote(value: str, original: str) -> str:
    """原值带引号就沿用同样的引号，避免写回后语义变化。"""
    if original[:1] in ("'", '"') and original[-1:] == original[:1]:
        quote = original[0]
        return f"{quote}{value}{quote}"
    return value


def process(path: Path, keys: tuple[str, ...], *, check_only: bool) -> int:
    if not path.exists():
        print(f"未找到 {path}，请先从 .env.example 复制一份")
        return 2

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    changed: list[str] = []
    plaintext: list[str] = []

    for index, line in enumerate(lines):
        parsed = _split(line)
        if parsed is None:
            continue
        key, value = parsed
        if key not in keys or not value:
            continue
        if is_encrypted(value):
            print(f"[已加密] {key} = {mask(value)}")
            continue
        plaintext.append(key)
        if check_only:
            print(f"[明文]   {key} = {mask(value)}  ← 建议加密")
            continue
        encrypted = encrypt_value(value)
        newline = "\n" if line.endswith("\n") else ""
        lines[index] = f"{key}={_quote(encrypted, value)}{newline}"
        changed.append(key)
        print(f"[加密]   {key}：{mask(value)} → {mask(encrypted)}")

    if check_only:
        if plaintext:
            print(f"\n共 {len(plaintext)} 项仍是明文：{', '.join(plaintext)}")
            print(f"执行 `python -m scripts.encrypt_secrets` 加密；主密钥放在 SECRETS_MASTER_KEY。")
            return 1
        print("\n全部已加密。")
        return 0

    if not changed:
        print("\n没有需要处理的项。")
        return 0

    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copyfile(path, backup)
    path.write_text("".join(lines), encoding="utf-8")
    print(f"\n已写回 {path}（备份：{backup.name}）")
    print(f"⚠ {backup.name} 里仍是**明文**密钥（仅供回滚），确认服务正常后请删除；“已加入 .gitignore”并不等于“已安全”。")
    print(f"主密钥提示：SECRETS_MASTER_KEY 未配置时会退回 SECRET_KEY 派生；生产环境必须显式配置。")
    print(f"密文前缀：{PREFIX}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="加密 .env 中的第三方密钥")
    parser.add_argument("--check", action="store_true", help="只检查，不修改文件")
    parser.add_argument("--keys", default="", help="逗号分隔的键名，默认 LLM_API_KEY,SMTP_PASSWORD")
    parser.add_argument("--file", default=str(ENV_PATH), help="要处理的 .env 路径")
    args = parser.parse_args(argv)

    keys = tuple(item.strip() for item in args.keys.split(",") if item.strip()) or DEFAULT_KEYS
    return process(Path(args.file), keys, check_only=args.check)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
