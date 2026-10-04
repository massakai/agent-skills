"""文書検査スクリプトの境界とリンク検証を検証するテスト。"""

import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_docs.py"
spec = importlib.util.spec_from_file_location("check_docs", SCRIPT)
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


class DocumentChecks(unittest.TestCase):
    """合成リポジトリで文書検査の安全な境界を検証する。"""

    def setUp(self):
        """各テスト用の一時リポジトリを準備する。"""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, text):
        """指定した相対パスにテスト文書を書き込む。"""
        file = self.root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)

    def test_inline_reference_unicode_duplicate_and_space(self):
        """Unicodeアンカーと空白を含む有効な参照を受理することを確認する。"""
        self.write("guide.md", "[link](<space name.md#日本語-見出し-1>)\n[ref][target]\n[target]: space%20name.md#日本語-見出し\n")
        self.write("space name.md", "# 日本語 見出し\n# 日本語 見出し\n")
        self.assertEqual([], docs.check(self.root, ["guide.md"])["errors"])

    def test_missing_anchor_and_reference(self):
        """存在しないアンカーと参照を個別のエラーとして検出する。"""
        self.write("guide.md", "[missing](#bad)\n[ref][unknown]\n# Good\n")
        self.assertEqual(2, len(docs.check(self.root, ["guide.md"])["errors"]))

    def test_parent_escape_and_symlink(self):
        """親ディレクトリ脱出と外部シンボリックリンクを拒否する。"""
        self.write("guide.md", "[parent](../outside.md)\n[symlink](outside.md)\n")
        (self.root / "outside.md").symlink_to(self.root.parent / "outside.md")
        self.assertEqual(2, len(docs.check(self.root, ["guide.md"])["errors"]))

    def test_internal_parent_reference_is_valid(self):
        """リポジトリ内の親相対リンクは有効として扱う。"""
        self.write("guide.md", "# Good\n")
        self.write("nested/readme.md", "[parent](../guide.md#good)\n")
        self.assertEqual([], docs.check(self.root, ["nested/readme.md"])["errors"])

    def test_fenced_links_ignored_but_local_paths_scanned(self):
        """コードフェンス内のリンクを除外し、絶対ローカルパスは検査する。"""
        self.write("guide.md", "```md\n[example](missing.md)\n```\n```sh\ncat /home/example/config\n```\n")
        result = docs.check(self.root, ["guide.md"])
        self.assertEqual(0, result["links_checked"])
        self.assertEqual(1, len(result["errors"]))

    def test_external_source_symlink_not_read(self):
        """外部を指す入力シンボリックリンクを読み込まずエラーにする。"""
        (self.root / "guide.md").symlink_to(self.root.parent / "missing.md")
        self.assertEqual(1, len(docs.check(self.root, ["guide.md"])["errors"]))

    def test_fenced_fake_heading_does_not_create_anchor(self):
        """コードフェンス内の見出しをアンカーとして登録しない。"""
        self.write("guide.md", "[bad](#fake)\n```\n# Fake\n```\n")
        self.assertEqual(1, len(docs.check(self.root, ["guide.md"])["errors"]))


if __name__ == "__main__":
    unittest.main()
