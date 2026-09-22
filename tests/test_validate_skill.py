"""scripts.validate_skill の公開検証契約を確認する。"""

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_skill.py"
SPEC = importlib.util.spec_from_file_location("validate_skill", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class ValidateSkillTest(unittest.TestCase):
    """SKILL.md の形式・必須項目・TODO 検出を確認する。"""

    def write_skill(self, body: str) -> Path:
        """一時ディレクトリに検証対象の SKILL.md を作成する。"""
        directory = Path(tempfile.mkdtemp())
        (directory / "SKILL.md").write_text(body, encoding="utf-8")
        self.addCleanup(shutil.rmtree, directory)
        return directory

    def test_validate_skill_returns_success_for_valid_skill(self) -> None:
        """有効な必須 frontmatter を受理する。"""
        skill = self.write_skill(
            "---\nname: sample-skill\ndescription: 有効な説明です。\n---\n\n# Sample\n"
        )

        actual, message = VALIDATOR.validate_skill(skill)

        self.assertTrue(actual)
        self.assertEqual(message, "スキルは有効です。")

    def test_validate_skill_rejects_unknown_frontmatter_key(self) -> None:
        """許可していない frontmatter キーを拒否する。"""
        skill = self.write_skill(
            "---\nname: sample-skill\ndescription: 有効な説明です。\nunknown: value\n---\n"
        )

        actual, message = VALIDATOR.validate_skill(skill)

        self.assertFalse(actual)
        self.assertIn("許可されない", message)

    def test_validate_skill_rejects_todo_outside_code_fence(self) -> None:
        """本文に残った TODO プレースホルダーを拒否する。"""
        skill = self.write_skill(
            "---\nname: sample-skill\ndescription: 有効な説明です。\n---\n\n[TODO: 完了する]\n"
        )

        actual, message = VALIDATOR.validate_skill(skill)

        self.assertFalse(actual)
        self.assertIn("TODO", message)

    def test_validate_skill_allows_todo_in_code_fence(self) -> None:
        """コード例に含まれる TODO はプレースホルダーとして扱わない。"""
        skill = self.write_skill(
            "---\nname: sample-skill\ndescription: 有効な説明です。\n---\n\n```text\n[TODO: 例]\n```\n"
        )

        actual, message = VALIDATOR.validate_skill(skill)

        self.assertTrue(actual)
        self.assertEqual(message, "スキルは有効です。")
