"""preflight.inspect_publishの読み取り専用レポート契約を合成環境で検証する。"""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import preflight
import workflow

SPEC = importlib.util.spec_from_file_location("preflight_fixtures", ROOT / "tests/test_workflow.py")
fixtures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixtures)


class PreflightTests(unittest.TestCase):
    """外部接続を合成化し、結果分類と副作用の境界を確認する。"""

    setUp = fixtures.WorkflowTestCase.setUp
    args = fixtures.WorkflowTestCase.args
    make_branch = fixtures.WorkflowTestCase.make_branch

    def prepare(self):
        """検証対象の合成planとファイルを作り、現在の確認値を記録する。"""
        self.make_branch()
        (self.root / "guide.md").write_text("synthetic\n")
        snap = workflow.fingerprint(self.root)
        self.plan_file = Path(self.tmp.name) / "plan.json"
        self.plan = {"version": "workflow-plan/v1", "purpose": "合成手順の更新",
                     "destination": {"host": "github.com", "repository": "example/project", "remote": "origin",
                                     "base": "master", "branch": "codex/test"},
                     "paths": ["guide.md"], "title": "合成手順の更新", "labels": ["codex"],
                     "operations": ["commit", "push", "pr"],
                     "request": {"reference": "current user request", "state": "confirmed"},
                     "validation": {"state": "passed", "head": snap["head"], "snapshot_state": snap["state"],
                                    "reference": "synthetic validation log", "reason": ""},
                     "body_requirements": {"marker": "# Summary", "headings": ["# Validation"], "labels": ["codex"]}}
        self.save_plan()

    def save_plan(self):
        """合成planをcheckout外の一時領域へ保存する。"""
        self.plan_file.write_text(json.dumps(self.plan))

    def inspect(self, factory=fixtures.FakeWorkflow):
        """指定した合成境界を使い、公開前検査を実行する。"""
        return preflight.inspect_publish(self.root, self.plan_file, self.body_file, "合成手順の変更", factory)

    def test_success_report_preserves_head_index_and_worktree(self):
        # Given
        self.prepare()
        before = workflow.fingerprint(self.root)
        # When
        report, code = self.inspect()
        # Then
        self.assertEqual((code, report["result"]), (0, "satisfied"))
        self.assertEqual(report["schema_version"], "workflow-evidence/v1")
        self.assertEqual(report["inputs"]["publication_sha256"], workflow.publish_plan.canonical_digest(report["publication"]))
        self.assertEqual(before, workflow.fingerprint(self.root))
        self.assertIsNone(fixtures.FakeWorkflow(self.args("publish")).remote_head())

    def test_unresolved_request_is_blocked(self):
        # Given
        self.prepare()
        self.plan["request"]["state"] = "unresolved"
        self.save_plan()
        # When
        report, code = self.inspect()
        # Then
        self.assertEqual((code, report["findings"][0]["code"]), (1, "PLAN_UNRESOLVED"))

    def test_required_commit_message_is_checked_without_staging(self):
        # Given
        self.prepare()
        before = workflow.fingerprint(self.root)
        # When
        report, code = preflight.inspect_publish(self.root, self.plan_file, self.body_file, None, fixtures.FakeWorkflow)
        # Then
        self.assertEqual((code, report["findings"][0]["code"]), (1, "COMMIT_MESSAGE_REQUIRED"))
        self.assertEqual(before, workflow.fingerprint(self.root))

    def test_invalid_plan_is_rejected_before_workflow_creation(self):
        # Given
        self.prepare()
        self.plan["secret-extra"] = "sensitive-value"
        self.save_plan()
        factory = mock.Mock()
        # When
        report, code = self.inspect(factory)
        # Then
        self.assertEqual((code, report["findings"][0]["code"]), (2, "INVALID_PLAN"))
        factory.assert_not_called()
        self.assertNotIn("sensitive-value", json.dumps(report))

    def test_environment_failure_is_unavailable_without_exception_details(self):
        # Given
        self.prepare()
        factory = mock.Mock(side_effect=OSError("sensitive-value"))
        # When
        report, code = self.inspect(factory)
        # Then
        self.assertEqual((code, report["result"]), (4, "unavailable"))
        self.assertNotIn("sensitive-value", json.dumps(report))

    def test_malformed_remote_response_is_not_invalid_plan(self):
        # Given
        self.prepare()
        factory = mock.Mock()
        factory.return_value.execute.side_effect = ValueError("remote response invalid")
        factory.return_value.data = {}
        # When
        report, code = self.inspect(factory)
        # Then
        self.assertEqual((code, report["findings"][0]["code"]), (4, "CHECK_UNAVAILABLE"))

    def test_plan_strings_are_values_and_not_cli_options(self):
        # Given
        self.prepare()
        self.plan["title"] = "--help"
        self.plan["paths"] = ["-guide.md"]
        # When
        args = preflight.publish_args(self.root, self.plan, self.body_file)
        # Then
        self.assertEqual(args.title, "--help")
        self.assertEqual(args.path, ["-guide.md"])
        self.assertFalse(args.apply)

    def test_cli_invalid_plan_prints_one_json_document(self):
        # Given
        self.prepare()
        self.plan_file.write_text('{"version":"private-value"}')
        # When
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/preflight.py"), "publish",
                                 "--repo", str(self.root), "--plan", str(self.plan_file),
                                 "--body-file", str(self.body_file)], text=True, capture_output=True)
        # Then
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["findings"][0]["code"], "INVALID_PLAN")
        self.assertNotIn("private-value", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
