#!/usr/bin/env python3
"""リポジトリ内の SKILL.md frontmatter を検証する。"""

import re
import sys
from pathlib import Path

import yaml


MAX_SKILL_NAME_LENGTH = 64
ALLOWED_FRONTMATTER_KEYS = {
    "name",
    "description",
    "license",
    "allowed-tools",
    "metadata",
}


def validate_skill(skill_path: Path) -> tuple[bool, str]:
    """指定スキルの必須 frontmatter と未完了プレースホルダーを検証する。"""
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return False, "SKILL.md が見つかりません。"

    content = skill_md.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return False, "YAML frontmatter がありません。"

    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return False, "frontmatter の形式が不正です。"

    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError as error:
        return False, f"frontmatter の YAML が不正です: {error}"

    if not isinstance(frontmatter, dict):
        return False, "frontmatter は YAML mapping でなければなりません。"

    unexpected_keys = set(frontmatter) - ALLOWED_FRONTMATTER_KEYS
    if unexpected_keys:
        unexpected = ", ".join(sorted(unexpected_keys))
        return False, f"許可されない frontmatter キーがあります: {unexpected}"

    name = frontmatter.get("name")
    if not isinstance(name, str):
        return False, "name は文字列でなければなりません。"
    name = name.strip()
    if name and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        return False, "name は小文字、数字、ハイフンだけの kebab-case にしてください。"
    if len(name) > MAX_SKILL_NAME_LENGTH:
        return False, f"name は {MAX_SKILL_NAME_LENGTH} 文字以下にしてください。"

    description = frontmatter.get("description")
    if not isinstance(description, str):
        return False, "description は文字列でなければなりません。"
    description = description.strip()
    if description.startswith("[TODO:"):
        return False, "description に未完了の TODO があります。"
    if description and ("<" in description or ">" in description):
        return False, "description に山かっこは使えません。"
    if len(description) > 1024:
        return False, "description は 1024 文字以下にしてください。"

    fence_marker: str | None = None
    fence_length = 0
    for line in content[match.end() :].splitlines():
        fence = re.match(
            r"^[ \t]*(?:(?:[-+*]|\d+[.)])[ \t]+)?(`{3,}|~{3,})(.*)$", line
        )
        if fence:
            marker = fence.group(1)
            if fence_marker is None:
                fence_marker = marker[0]
                fence_length = len(marker)
            elif (
                marker[0] == fence_marker
                and len(marker) >= fence_length
                and not fence.group(2).strip()
            ):
                fence_marker = None
                fence_length = 0
            continue

        if fence_marker is None and re.fullmatch(
            r"[ ]{0,3}\[TODO:[^\n]*\][ \t]*", line
        ):
            return False, "スキル本文に未完了の TODO があります。"

    return True, "スキルは有効です。"


def main() -> int:
    """コマンドライン引数のスキルディレクトリを検証して終了コードを返す。"""
    if len(sys.argv) != 2:
        print("使い方: python scripts/validate_skill.py <skill_directory>")
        return 1

    valid, message = validate_skill(Path(sys.argv[1]))
    print(message)
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
