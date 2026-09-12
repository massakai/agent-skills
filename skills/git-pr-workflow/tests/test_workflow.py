"""Integration-style tests for the bounded Git/gh workflow.

The tests use disposable local repositories and a fake ``gh`` boundary.  They
never contact GitHub or use a developer checkout.
"""

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "workflow.py"
SPEC = importlib.util.spec_from_file_location("workflow", SCRIPT)
workflow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(workflow)


def git(cwd, *args, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, text=True,
                          capture_output=True)


class FakeWorkflow(workflow.Workflow):
    """Real Git, with only the GitHub command boundary replaced."""

    def __init__(self, args, replies=None):
        super().__init__(args)
        self.replies = replies or {}
        self.gh_calls = []

    def authenticate(self):
        # The workflow normally proves this against GitHub.  Tests deliberately
        # keep that boundary synthetic while preserving all local Git behavior.
        self.github = "https://github.com/example/project"

    def gh(self, *args, check=True):
        self.gh_calls.append(args)
        key = " ".join(args[:3])
        value = self.replies.get(key, self.replies.get(args[0], "[]"))
        if isinstance(value, list):
            value = value.pop(0) if value else "[]"
        if isinstance(value, tuple):
            code, text = value
        else:
            code, text = 0, value
        return subprocess.CompletedProcess(["gh", *args], code, text, "")


class WorkflowTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.remote = Path(self.tmp.name) / "remote.git"
        self.root.mkdir()
        git(self.root, "init", "-b", "master")
        git(self.root, "config", "user.name", "Workflow Test")
        git(self.root, "config", "user.email", "workflow@example.invalid")
        (self.root / "README.md").write_text("seed\n")
        git(self.root, "add", "README.md")
        git(self.root, "commit", "-m", "seed")
        git(self.tmp.name, "init", "--bare", str(self.remote))
        git(self.root, "remote", "add", "origin", str(self.remote))
        git(self.root, "push", "-u", "origin", "master")
        self.body_file = Path(self.tmp.name) / "body.md"
        self.body_file.write_text("# Summary\n\nA multiline body.\n\n# Validation\n\nSynthetic only.\n")

    def args(self, command, **overrides):
        data = dict(command=command, repo=str(self.root), github_repo="example/project",
                    remote="origin", base="master", branch="codex/test", worktree=str(Path(self.tmp.name) / "wt"),
                    pr=None, path=[], message="テストの変更", title="Synthetic workflow test",
                    body_file=str(self.body_file), label=["codex"], ssh_public_key=None,
                    mapping=None, inactive=False, apply=False, expected_head=None,
                    expected_state=None, expected_body=None)
        data.update(overrides)
        return argparse.Namespace(**data)

    def make_branch(self, name="codex/test"):
        git(self.root, "checkout", "-b", name)

    def open_pr(self, number=7, head=None, body=None, title=None, labels=None, state="OPEN"):
        head = head or git(self.root, "rev-parse", "HEAD").stdout.strip()
        return {"number": number, "url": f"https://github.com/example/project/pull/{number}",
                "state": state, "baseRefName": "master", "headRefName": "codex/test",
                "headRefOid": head, "isCrossRepository": False, "mergeCommit": {"oid": head},
                "labels": [{"name": x} for x in (labels if labels is not None else ["codex"])],
                "title": title or "Synthetic workflow test", "body": body if body is not None else self.body_file.read_text()}

    def run_execute(self, args, replies=None):
        w = FakeWorkflow(args, replies)
        w.execute()
        return w

    def test_prepare_preview_reports_target_without_creating_it(self):
        target = Path(self.args("prepare").worktree)
        w = self.run_execute(self.args("prepare"))
        self.assertFalse(target.exists())
        self.assertEqual(w.data["worktree"], str(target.resolve()))
        self.assertEqual(w.remaining, ["fetch_base", "fast_forward_base", "create_worktree", "verify_worktree"])

    def test_prepare_apply_rejects_stale_preview_state(self):
        preview = FakeWorkflow(self.args("prepare"))
        snap = preview.snapshot()
        (self.root / "after-preview.txt").write_text("changed after preview")
        git(self.root, "add", "after-preview.txt")
        git(self.root, "commit", "-m", "change after preview")
        args = self.args("prepare", apply=True, expected_head=snap["head"], expected_state=snap["state"])
        with self.assertRaisesRegex(workflow.Stop, "changed/unconfirmed"):
            self.run_execute(args)
        self.assertFalse(Path(args.worktree).exists())

    def test_prepare_worktree_creation_failure_does_not_continue(self):
        args = self.args("prepare", apply=True)
        snap = FakeWorkflow(args).snapshot()
        args.expected_head, args.expected_state = snap["head"], snap["state"]
        class FailingAdd(FakeWorkflow):
            def git(self, *call, **kwargs):
                if call[:2] == ("worktree", "add"):
                    self.add_attempted = True
                    raise workflow.Stop("synthetic worktree add failure")
                return super().git(*call, **kwargs)
        w = FailingAdd(args)
        with self.assertRaisesRegex(workflow.Stop, "worktree add failure"):
            w.execute()
        self.assertTrue(w.add_attempted)
        self.assertEqual(w.completed, ["fetch_base", "fast_forward_base"])
        self.assertFalse(Path(args.worktree).exists())

    def test_publish_stages_only_requested_space_path_and_commits_pushes(self):
        self.make_branch()
        wanted = "name with spaces.txt"
        (self.root / wanted).write_text("wanted\n")
        (self.root / "unrelated.txt").write_text("leave untracked\n")
        args = self.args("publish", apply=True, path=[wanted])
        pre = FakeWorkflow(args)
        snap = pre.snapshot()
        args.expected_head, args.expected_state = snap["head"], snap["state"]
        args.expected_body = __import__("hashlib").sha256(self.body_file.read_bytes()).hexdigest()
        # First lookup finds none; post-push readback finds the PR at the pushed SHA.
        class Readback(FakeWorkflow):
            def gh(self, *call, check=True):
                self.gh_calls.append(call)
                if call[:2] == ("pr", "list"):
                    self.listed = getattr(self, "listed", 0) + 1
                    text = "[]" if self.listed < 3 else json.dumps([{"number": 7}])
                    return subprocess.CompletedProcess([], 0, text, "")
                if call[:3] == ("pr", "view", "7"):
                    p = self_case.open_pr(head=git(self_case.root, "rev-parse", "HEAD").stdout.strip())
                    return subprocess.CompletedProcess([], 0, json.dumps(p), "")
                return subprocess.CompletedProcess([], 0, "created\n", "")
        self_case = self
        w = Readback(args)
        w.execute()
        self.assertEqual(w.data["staged_paths"], [wanted])
        self.assertEqual(git(self.root, "show", "--format=%s", "-s").stdout.strip(), "テストの変更")
        self.assertEqual(git(self.root, "ls-remote", "--heads", "origin", "refs/heads/codex/test").returncode, 0)
        self.assertTrue((self.root / "unrelated.txt").exists())
        self.assertIn("pr_verified", w.completed)

    def test_publish_refuses_unrelated_already_staged_file(self):
        self.make_branch()
        (self.root / "wanted.txt").write_text("wanted")
        (self.root / "other.txt").write_text("other")
        git(self.root, "add", "other.txt")
        with self.assertRaisesRegex(workflow.Stop, "Unrelated staged"):
            FakeWorkflow(self.args("publish", path=["wanted.txt"])).publish(False)
        self.assertEqual(git(self.root, "rev-parse", "HEAD").stdout.strip(), git(self.root, "rev-parse", "HEAD").stdout.strip())

    def test_push_remote_success_then_local_tracking_failure_does_not_repush(self):
        self.make_branch()
        (self.root / "x").write_text("x")
        git(self.root, "add", "x")
        git(self.root, "commit", "-m", "x")
        args = self.args("publish")
        w = FakeWorkflow(args)
        original = w.repair_tracking
        calls = []
        def broken_repair():
            calls.append("repair")
            raise workflow.Stop("local tracking unavailable")
        w.repair_tracking = broken_repair
        with self.assertRaisesRegex(workflow.Stop, "tracking"):
            w.push()
        self.assertEqual(calls, ["repair"])
        self.assertEqual(w.completed, ["push_confirmed"])
        self.assertEqual(w.remote_head(), git(self.root, "rev-parse", "HEAD").stdout.strip())
        w.repair_tracking = original

    def test_publish_ambiguous_create_failure_reads_back_existing_pr_without_retry(self):
        self.make_branch()
        (self.root / "wanted.txt").write_text("wanted")
        args = self.args("publish", apply=True, path=["wanted.txt"])
        snap = FakeWorkflow(args).snapshot()
        args.expected_head, args.expected_state = snap["head"], snap["state"]
        args.expected_body = __import__("hashlib").sha256(self.body_file.read_bytes()).hexdigest()
        # The post-push lookup returns a PR despite gh create returning failure.
        pushed_head = None
        calls = 0
        def listed():
            nonlocal pushed_head, calls
            calls += 1
            if calls < 3:
                return "[]"
            pushed_head = git(self.root, "rev-parse", "HEAD").stdout.strip()
            return json.dumps([{"number": 7}])
        class Dynamic(FakeWorkflow):
            def gh(self, *call, check=True):
                self.gh_calls.append(call)
                if call[:2] == ("pr", "list"):
                    return subprocess.CompletedProcess([], 0, listed(), "")
                if call[:3] == ("pr", "view", "7"):
                    return subprocess.CompletedProcess([], 0, json.dumps(self_case.open_pr(head=git(self.root, "rev-parse", "HEAD").stdout.strip())), "")
                if call[:2] == ("pr", "create"):
                    return subprocess.CompletedProcess([], 1, "network uncertain", "")
                return subprocess.CompletedProcess([], 0, "[]", "")
        self_case = self
        w = Dynamic(args)
        w.execute()
        self.assertEqual(sum(c[:2] == ("pr", "create") for c in w.gh_calls), 1)
        self.assertIn("pr_verified", w.completed)

    def test_publish_resume_after_commit_and_push_does_not_create_another_commit(self):
        self.make_branch()
        (self.root / "wanted.txt").write_text("wanted")
        git(self.root, "add", "wanted.txt")
        git(self.root, "commit", "-m", "already committed")
        git(self.root, "push", "origin", "HEAD:refs/heads/codex/test")
        args = self.args("publish", apply=True, path=[])
        snap = FakeWorkflow(args).snapshot()
        args.expected_head, args.expected_state = snap["head"], snap["state"]
        args.expected_body = __import__("hashlib").sha256(self.body_file.read_bytes()).hexdigest()
        before = git(self.root, "rev-list", "--count", "HEAD").stdout
        pr = self.open_pr()
        replies = {"pr list --repo": [json.dumps([{"number": 7}]), json.dumps([{"number": 7}]), json.dumps([{"number": 7}])],
                   "pr view 7": json.dumps(pr), "pr edit 7": (0, "edited")}
        self.run_execute(args, replies)
        self.assertEqual(git(self.root, "rev-list", "--count", "HEAD").stdout, before)

    def test_feedback_paginates_deduplicates_and_preserves_obsolete_line_mapping(self):
        self.make_branch()
        pr = self.open_pr(state="MERGED")
        inline = [[{"id": 1, "body": "old", "html_url": "u", "path": "x.py", "line": None,
                    "original_line": 12, "commit_id": "old", "in_reply_to_id": None}],
                  [{"id": 1, "body": "duplicate", "html_url": "u"}]]
        mapping = Path(self.tmp.name) / "mapping.json"
        mapping.write_text(json.dumps({"inline:1": {"response": "will update", "reply_draft": "thanks"}}))
        args = self.args("feedback", pr=7, mapping=str(mapping))
        replies = {"pr view 7": json.dumps(pr), "api --hostname github.com": [json.dumps(inline), "[[]]", "[[]]"]}
        w = self.run_execute(args, replies)
        self.assertEqual(len(w.data["feedback"]), 1)
        record = w.data["feedback"][0]
        self.assertIsNone(record["line"])
        self.assertEqual(record["original_line"], 12)
        self.assertEqual(record["reply_draft"], "thanks")

    def test_cleanup_refuses_ignored_files_and_extra_branch_commit(self):
        self.make_branch()
        (self.root / "extra.txt").write_text("extra")
        git(self.root, "add", "extra.txt")
        git(self.root, "commit", "-m", "extra after merge")
        git(self.root, "checkout", "master")
        target = Path(self.args("cleanup").worktree)
        git(self.root, "worktree", "add", "--detach", str(target))
        (target / ".gitignore").write_text("ignored\n")
        (target / "ignored").write_text("keep")
        # Branch moved beyond the advertised merged PR head.
        pr = self.open_pr(head=git(self.root, "rev-parse", "codex/test~1").stdout.strip(), state="MERGED")
        args = self.args("cleanup", inactive=True, pr=7, worktree=str(target))
        with self.assertRaisesRegex(workflow.Stop, "differs from the merged PR head"):
            self.run_execute(args, {"pr view 7": json.dumps(pr)})

    def test_cleanup_refuses_ignored_files_even_when_pr_head_matches(self):
        self.make_branch()
        (self.root / "merged.txt").write_text("merged")
        (self.root / ".gitignore").write_text("ignored\n")
        git(self.root, "add", "merged.txt", ".gitignore")
        git(self.root, "commit", "-m", "merged")
        head = git(self.root, "rev-parse", "HEAD").stdout.strip()
        git(self.root, "checkout", "master")
        target = Path(self.args("cleanup").worktree)
        git(self.root, "worktree", "add", str(target), "codex/test")
        (target / "ignored").write_text("preserve")
        args = self.args("cleanup", inactive=True, pr=7, worktree=str(target))
        pr = self.open_pr(head=head, state="MERGED")
        with self.assertRaisesRegex(workflow.Stop, "requiring preservation"):
            self.run_execute(args, {"pr view 7": json.dumps(pr)})

    def test_cleanup_apply_removes_clean_merged_worktree_when_merge_is_in_base(self):
        self.make_branch()
        (self.root / "merged.txt").write_text("merged")
        git(self.root, "add", "merged.txt")
        git(self.root, "commit", "-m", "merged")
        head = git(self.root, "rev-parse", "HEAD").stdout.strip()
        # Model a merge by advancing master to this commit; safe branch deletion is then possible.
        git(self.root, "checkout", "master")
        git(self.root, "merge", "--ff-only", head)
        git(self.root, "push", "origin", "master")
        target = Path(self.args("cleanup").worktree)
        git(self.root, "worktree", "add", str(target), "codex/test")
        args = self.args("cleanup", inactive=True, pr=7, worktree=str(target), apply=True)
        snap = FakeWorkflow(args).snapshot()
        args.expected_head, args.expected_state = snap["head"], snap["state"]
        pr = self.open_pr(head=head, state="MERGED")
        w = self.run_execute(args, {"pr view 7": json.dumps(pr)})
        self.assertFalse(target.exists())
        self.assertNotEqual(git(self.root, "show-ref", "--verify", "--quiet", "refs/heads/codex/test", check=False).returncode, 0)
        self.assertEqual(w.completed[-2:], ["remove_worktree", "delete_branch"])

    def test_body_requires_all_template_headings_and_preserves_multiline_text(self):
        template = self.root / ".github" / "pull_request_template.md"
        template.parent.mkdir()
        template.write_text("# Summary\n# Validation\n")
        args = self.args("publish")
        w = FakeWorkflow(args)
        self.assertEqual(w.body(), self.body_file.read_text())
        self.body_file.write_text("# Summary\n")
        with self.assertRaisesRegex(workflow.Stop, "template heading"):
            w.body()

    def test_parser_enforces_minimal_publish_and_read_only_feedback(self):
        p = workflow.parser()
        parsed = p.parse_args(["publish", "--repo", "r", "--github-repo", "x/y", "--base", "master",
                               "--branch", "topic", "--title", "t", "--body-file", "b"])
        self.assertEqual(parsed.command, "publish")
        with self.assertRaises(SystemExit):
            workflow.main(["feedback", "--repo", "r", "--github-repo", "x/y", "--base", "master",
                           "--branch", "topic", "--pr", "1", "--apply"])

    def test_verify_remote_accepts_normal_ssh_https_and_rejects_mismatch_or_duplicates(self):
        info = {"url": "https://github.com/example/project", "nameWithOwner": "example/project"}
        class RemoteWorkflow(FakeWorkflow):
            def __init__(self, args, fetch, push):
                super().__init__(args)
                self.fetch, self.push = fetch, push
            def git(self, *call, **kwargs):
                if call[:3] == ("remote", "get-url", "--all"):
                    return subprocess.CompletedProcess([], 0, self.fetch, "")
                if call[:4] == ("remote", "get-url", "--push", "--all"):
                    return subprocess.CompletedProcess([], 0, self.push, "")
                raise AssertionError(f"unexpected git call: {call}")
        valid = RemoteWorkflow(self.args("prepare"), "git@github.com:example/project.git\n",
                               "https://github.com/example/project.git\n")
        valid.verify_remote(info)
        mismatch = RemoteWorkflow(self.args("prepare"), "git@github.com:example/project.git\n",
                                  "https://github.com/example/other.git\n")
        with self.assertRaisesRegex(workflow.Stop, "does not match"):
            mismatch.verify_remote(info)
        duplicate = RemoteWorkflow(self.args("prepare"), "git@github.com:example/project.git\nhttps://github.com/example/project.git\n",
                                   "https://github.com/example/project.git\n")
        with self.assertRaisesRegex(workflow.Stop, "Exactly one"):
            duplicate.verify_remote(info)

    def test_publish_stops_before_commit_when_state_changes_after_preview(self):
        self.make_branch()
        (self.root / "wanted.txt").write_text("wanted")
        args = self.args("publish", apply=True, path=["wanted.txt"])
        snap = FakeWorkflow(args).snapshot()
        args.expected_head, args.expected_state = snap["head"], snap["state"]
        args.expected_body = __import__("hashlib").sha256(self.body_file.read_bytes()).hexdigest()
        class MutatingLookup(FakeWorkflow):
            def matching_pr(self):
                (self.root / "raced.txt").write_text("changed after preview")
                self.git("add", "raced.txt")
                return None
        w = MutatingLookup(args)
        before = git(self.root, "rev-parse", "HEAD").stdout.strip()
        with self.assertRaisesRegex(workflow.Stop, "changed/unconfirmed"):
            w.execute()
        self.assertEqual(git(self.root, "rev-parse", "HEAD").stdout.strip(), before)
        self.assertNotIn("commit", w.completed)

    def test_cleanup_stops_when_merge_commit_is_not_in_fetched_base(self):
        self.make_branch()
        (self.root / "merged.txt").write_text("merged")
        git(self.root, "add", "merged.txt")
        git(self.root, "commit", "-m", "merged")
        head = git(self.root, "rev-parse", "HEAD").stdout.strip()
        git(self.root, "checkout", "master")
        git(self.root, "merge", "--ff-only", head)
        git(self.root, "push", "origin", "master")
        target = Path(self.args("cleanup").worktree)
        git(self.root, "worktree", "add", str(target), "codex/test")
        args = self.args("cleanup", inactive=True, pr=7, worktree=str(target), apply=True)
        snap = FakeWorkflow(args).snapshot()
        args.expected_head, args.expected_state = snap["head"], snap["state"]
        pr = self.open_pr(head=head, state="MERGED")
        pr["mergeCommit"] = {"oid": "0" * 40}
        w = FakeWorkflow(args, {"pr view 7": json.dumps(pr)})
        with self.assertRaisesRegex(workflow.Stop, "not present"):
            w.execute()
        self.assertTrue(target.exists())
        self.assertEqual(w.completed, ["fetch_base"])

    def test_matching_pr_rejects_ambiguous_and_explicit_wrong_repository_or_base(self):
        args = self.args("publish", pr=None)
        w = FakeWorkflow(args, {"pr list --repo": json.dumps([{"number": 1}, {"number": 2}])})
        with self.assertRaisesRegex(workflow.Stop, "Multiple PRs"):
            w.matching_pr()
        for field, value in (("isCrossRepository", True), ("baseRefName", "other")):
            with self.subTest(field=field):
                pr = self.open_pr()
                pr[field] = value
                explicit = FakeWorkflow(self.args("publish", pr=7), {"pr view 7": json.dumps(pr)})
                with self.assertRaisesRegex(workflow.Stop, "state/base/head/repository"):
                    explicit.matching_pr()


if __name__ == "__main__":
    unittest.main()
