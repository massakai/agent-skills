"""Workflow.publishの公開追加guardとpreview不変条件を検証する。"""

import importlib.util
import json
from pathlib import Path
import sys
import unittest


TESTS = Path(__file__).resolve().parent
SCRIPTS = TESTS.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
try:
    SPEC = importlib.util.spec_from_file_location("publication_base_tests", TESTS / "test_workflow.py")
    base_tests = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(base_tests)
finally:
    sys.path.remove(str(SCRIPTS))

workflow = base_tests.workflow
git = base_tests.git
FakeWorkflow = base_tests.FakeWorkflow


class PublicationGuardTests(unittest.TestCase):
    """公開previewとapplyの追加照合を合成Git環境で確認する。"""

    setUp = base_tests.WorkflowTestCase.setUp
    args = base_tests.WorkflowTestCase.args
    make_branch = base_tests.WorkflowTestCase.make_branch
    open_pr = base_tests.WorkflowTestCase.open_pr

    def preview(self, args):
        """read-onlyの公開preview結果と引数を返す。"""
        args.apply = False
        result = FakeWorkflow(args)
        result.execute()
        return result

    def set_apply_expectations(self, args, preview):
        """preview結果からapplyに必要な既存確認値を設定する。"""
        args.apply = True
        args.expected_head = preview.data["snapshot"]["head"]
        args.expected_state = preview.data["snapshot"]["state"]
        args.expected_body = preview.data["body_sha256"]
        args.expected_publication = preview.data["publication_sha256"]

    def test_preview_reports_publication_digest_without_changing_head_or_index(self):
        # Given
        self.make_branch()
        (self.root / "wanted.txt").write_text("synthetic change\n")
        args = self.args("publish", path=["wanted.txt"])
        head_before = git(self.root, "rev-parse", "HEAD").stdout.strip()
        index_before = git(self.root, "write-tree").stdout.strip()
        # When
        result = self.preview(args)
        # Then
        self.assertRegex(result.data["publication_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(head_before, git(self.root, "rev-parse", "HEAD").stdout.strip())
        self.assertEqual(index_before, git(self.root, "write-tree").stdout.strip())

    def test_apply_requires_expected_publication_before_staging(self):
        # Given
        self.make_branch()
        (self.root / "wanted.txt").write_text("synthetic change\n")
        args = self.args("publish", path=["wanted.txt"])
        preview = self.preview(args)
        self.set_apply_expectations(args, preview)
        args.expected_publication = None
        head_before = git(self.root, "rev-parse", "HEAD").stdout.strip()
        # When / Then
        with self.assertRaisesRegex(workflow.Stop, "PUBLICATION_CHANGED"):
            FakeWorkflow(args).execute()
        self.assertEqual(head_before, git(self.root, "rev-parse", "HEAD").stdout.strip())
        self.assertEqual("", git(self.root, "diff", "--cached", "--name-only").stdout)

    def test_changed_title_labels_message_and_remote_endpoint_stop_before_stage(self):
        # Given
        self.make_branch()
        (self.root / "wanted.txt").write_text("synthetic change\n")
        for change in ("title", "labels", "message", "endpoint"):
            with self.subTest(change=change):
                args = self.args("publish", path=["wanted.txt"])
                preview = self.preview(args)
                self.set_apply_expectations(args, preview)
                if change == "title":
                    args.title = "Changed title"
                elif change == "labels":
                    args.label = ["different"]
                elif change == "message":
                    args.message = "Changed message"
                else:
                    alternate = Path(self.tmp.name) / "alternate.git"
                    git(self.tmp.name, "init", "--bare", str(alternate))
                    git(self.root, "remote", "set-url", "--push", "origin", str(alternate))
                head_before = git(self.root, "rev-parse", "HEAD").stdout.strip()
                index_before = git(self.root, "write-tree").stdout.strip()
                # When / Then
                with self.assertRaisesRegex(workflow.Stop, "PUBLICATION_CHANGED"):
                    FakeWorkflow(args).execute()
                self.assertEqual(head_before, git(self.root, "rev-parse", "HEAD").stdout.strip())
                self.assertEqual(index_before, git(self.root, "write-tree").stdout.strip())
                if change == "endpoint":
                    git(self.root, "remote", "set-url", "--push", "origin", str(self.remote))

    def test_outgoing_commit_with_unrequested_rename_source_is_rejected(self):
        # Given
        (self.root / "old.txt").write_text("seed\n")
        git(self.root, "add", "old.txt")
        git(self.root, "commit", "-m", "seed tracked file")
        git(self.root, "push", "origin", "master")
        self.make_branch()
        (self.root / "old.txt").rename(self.root / "new.txt")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "rename tracked file")
        args = self.args("publish", path=["new.txt"])
        # When / Then
        with self.assertRaisesRegex(workflow.Stop, "OUT_OF_SCOPE_COMMIT"):
            FakeWorkflow(args).execute()

    def plan_for(self, args, snap, **overrides):
        """現在の合成対象に一致するworkflow-plan/v1を生成する。"""
        plan = {
            "version": "workflow-plan/v1", "purpose": "synthetic publication",
            "destination": {"host": "github.com", "repository": "example/project",
                            "remote": args.remote, "base": args.base, "branch": args.branch},
            "paths": list(args.path), "title": args.title, "labels": list(args.label),
            "operations": ["commit", "push", "pr"],
            "request": {"reference": "synthetic user request", "state": "confirmed"},
            "validation": {"state": "passed", "head": snap["head"],
                           "snapshot_state": snap["state"], "reference": "synthetic checks", "reason": ""},
            "body_requirements": {"marker": "# Summary", "headings": ["# Summary", "# Validation"],
                                  "labels": ["codex"]},
        }
        plan.update(overrides)
        return plan

    def write_plan(self, plan):
        """planを使い捨てfixture内へ保存し、そのパスを返す。"""
        path = Path(self.tmp.name) / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        return str(path)

    def test_plan_unresolved_request_stale_evidence_and_missing_marker_are_rejected(self):
        # Given
        self.make_branch()
        (self.root / "wanted.txt").write_text("synthetic change\n")
        args = self.args("publish", path=["wanted.txt"])
        snap = FakeWorkflow(args).snapshot()
        cases = []
        unresolved = self.plan_for(args, snap)
        unresolved["request"]["state"] = "unresolved"
        cases.append(("PLAN_UNRESOLVED", unresolved))
        stale = self.plan_for(args, snap)
        stale["validation"]["head"] = "f" * 40
        cases.append(("VALIDATION_STALE", stale))
        marker = self.plan_for(args, snap)
        marker["body_requirements"]["marker"] = "missing marker"
        cases.append(("BODY_REQUIREMENT_MISSING", marker))
        for reason, plan in cases:
            with self.subTest(reason=reason):
                args.plan = self.write_plan(plan)
                # When / Then
                with self.assertRaisesRegex(workflow.Stop, reason):
                    FakeWorkflow(args).execute()

    def test_plan_digest_change_after_review_rejects_apply_before_staging(self):
        # Given
        self.make_branch()
        (self.root / "wanted.txt").write_text("synthetic change\n")
        args = self.args("publish", path=["wanted.txt"])
        snap = FakeWorkflow(args).snapshot()
        plan_path = self.write_plan(self.plan_for(args, snap))
        args.plan = plan_path
        preview = self.preview(args)
        self.set_apply_expectations(args, preview)
        plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        plan["purpose"] = "changed after review"
        Path(plan_path).write_text(json.dumps(plan), encoding="utf-8")
        head_before = git(self.root, "rev-parse", "HEAD").stdout.strip()
        # When / Then
        with self.assertRaisesRegex(workflow.Stop, "PLAN_MISMATCH|PUBLICATION_CHANGED"):
            FakeWorkflow(args).execute()
        self.assertEqual(head_before, git(self.root, "rev-parse", "HEAD").stdout.strip())
        self.assertEqual("", git(self.root, "diff", "--cached", "--name-only").stdout)

    def test_file_change_during_intent_recalculation_stops_before_commit(self):
        # Given
        self.make_branch()
        target = self.root / "wanted.txt"
        target.write_text("reviewed content\n")
        args = self.args("publish", path=["wanted.txt"])
        preview = self.preview(args)
        self.set_apply_expectations(args, preview)
        head_before = git(self.root, "rev-parse", "HEAD").stdout.strip()
        index_before = git(self.root, "write-tree").stdout.strip()

        class MutatingIntentWorkflow(FakeWorkflow):
            """2回目の公開意図取得時に対象内容を書き換える。"""

            def publication_intent(self, paths, body, existing):
                """再計算の競合窓でファイル内容を変更する。"""
                self.intent_calls = getattr(self, "intent_calls", 0) + 1
                if self.intent_calls == 2:
                    target.write_text("changed during intent recalculation\n")
                return super().publication_intent(paths, body, existing)

        # When / Then
        worker = MutatingIntentWorkflow(args)
        with self.assertRaisesRegex(workflow.Stop, "changed/unconfirmed"):
            worker.execute()
        self.assertNotIn("commit", worker.completed)
        self.assertEqual(head_before, git(self.root, "rev-parse", "HEAD").stdout.strip())
        self.assertEqual(index_before, git(self.root, "write-tree").stdout.strip())

    def test_push_endpoint_change_after_commit_stops_before_push(self):
        # Given
        self.make_branch()
        (self.root / "wanted.txt").write_text("reviewed content\n")
        args = self.args("publish", path=["wanted.txt"])
        preview = self.preview(args)
        self.set_apply_expectations(args, preview)
        alternate = Path(self.tmp.name) / "alternate.git"
        git(self.tmp.name, "init", "--bare", str(alternate))

        class ChangingEndpointWorkflow(FakeWorkflow):
            """commit完了直後にpush URLを合成bare remoteへ切り替える。"""

            def stage(self, name, action):
                """commit段階を完了してからpush先を変更する。"""
                result = super().stage(name, action)
                if name == "commit":
                    git(self.root, "remote", "set-url", "--push", "origin", str(alternate))
                return result

        # When / Then
        worker = ChangingEndpointWorkflow(args)
        with self.assertRaisesRegex(workflow.Stop, "PUBLICATION_CHANGED"):
            worker.execute()
        self.assertEqual(["commit"], worker.completed)
        self.assertNotIn("push_confirmed", worker.completed)
        remote_branch = git(self.tmp.name, "--git-dir", str(self.remote), "show-ref",
                            "--verify", "refs/heads/codex/test", check=False)
        self.assertNotEqual(0, remote_branch.returncode)


if __name__ == "__main__":
    unittest.main()
