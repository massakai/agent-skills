#!/usr/bin/env python3
"""Bounded Git/gh workflow. Python 3.10+, Git and authenticated gh required."""

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlparse


class Stop(RuntimeError):
    pass


def run(argv, cwd, check=True):
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode:
        # Do not echo potentially credential-bearing command arguments or stderr.
        raise Stop(f"{argv[0]} {argv[1]} failed (exit {result.returncode}); inspect locally before retry")
    return result


def fingerprint(root):
    """Include staged, unstaged and untracked bytes, not only porcelain status."""
    root = Path(root).resolve()
    g = lambda *a: run(["git", *a], root).stdout
    head = g("rev-parse", "HEAD").strip()
    branch = g("branch", "--show-current").strip()
    status = g("status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignored")
    digest = hashlib.sha256()
    for part in (str(root), head, branch, status, g("diff", "--binary"),
                 g("diff", "--cached", "--binary")):
        digest.update(part.encode())
        digest.update(b"\0")
    for name in g("ls-files", "--others", "--exclude-standard", "-z").split("\0"):
        if name:
            p = root / name
            digest.update(name.encode())
            if p.is_symlink():
                digest.update(str(p.readlink()).encode())
            elif p.is_file():
                digest.update(p.read_bytes())
    return {"head": head, "branch": branch, "state": digest.hexdigest(),
            "status": status.replace("\0", "\n").rstrip()}


@contextmanager
def writer_lock(root):
    common = Path(run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], root).stdout.strip())
    path = common / "skill-workflow.lock"
    try:
        handle = path.open("x")
    except FileExistsError as exc:
        raise Stop("Another workflow writer or an interrupted run holds the lock; verify its owner before removing it") from exc
    try:
        handle.close()
        yield
    finally:
        path.unlink()


class Workflow:
    def __init__(self, args):
        self.a = args
        self.root = Path(args.repo).resolve()
        self.completed = []
        self.remaining = []
        self.data = {}
        self.github = args.github_repo

    def git(self, *args, cwd=None, check=True):
        return run(["git", *args], cwd or self.root, check)

    def gh(self, *args, check=True):
        return run(["gh", *args], self.root, check)

    def stage(self, name, action):
        value = action()
        self.completed.append(name)
        if name in self.remaining:
            self.remaining.remove(name)
        return value

    def authenticate(self):
        self.gh("auth", "status")
        info = json.loads(self.gh("repo", "view", self.github, "--json", "nameWithOwner,url").stdout)
        if info["nameWithOwner"].lower() != self.github.lower():
            raise Stop("GitHub repository identity mismatch")
        self.github = info["url"]
        self.verify_remote(info)

    def verify_remote(self, info):
        expected = urlparse(info["url"])
        urls = []
        for extra in ([], ["--push"]):
            urls.extend(self.git("remote", "get-url", *extra, "--all", self.a.remote).stdout.splitlines())
        for url in urls:
            match = re.fullmatch(r"(?:[^/@:]+@)?([^/:]+):(.+)", url) if "://" not in url else None
            parsed = urlparse(url)
            host, path = (match[1], match[2]) if match else (parsed.hostname, parsed.path.lstrip("/"))
            if host != expected.hostname or path.removesuffix(".git").lower() != info["nameWithOwner"].lower():
                raise Stop("Fetch/push remote does not match the requested GitHub repository")
        if len(urls) != 2:
            raise Stop("Exactly one fetch and one push URL are required")

    def snapshot(self):
        target = Path(self.a.worktree).resolve() if self.a.command == "cleanup" else self.root
        snap = fingerprint(target)
        self.data["snapshot"] = snap
        return snap

    def guard(self, snap):
        if self.a.expected_head != snap["head"] or self.a.expected_state != snap["state"]:
            raise Stop("HEAD or working state changed/unconfirmed; run the preview and review again")

    def ensure_branch(self, snap):
        if not self.a.branch or snap["branch"] != self.a.branch or self.a.branch == self.a.base:
            raise Stop("Expected a named feature branch, not detached HEAD or the base branch")
        self.git("check-ref-format", "--branch", self.a.branch)

    def clean(self, root, ignored=False):
        args = ["status", "--porcelain=v1", "--untracked-files=all"]
        if ignored:
            args.append("--ignored")
        if self.git(*args, cwd=root).stdout:
            raise Stop("Working tree has changes or files requiring preservation" if ignored else "Working tree is not clean")

    def pr(self, number):
        return json.loads(self.gh("pr", "view", str(number), "--repo", self.github, "--json",
                                  "number,url,state,baseRefName,headRefName,headRefOid,isCrossRepository,mergeCommit,labels,title,body").stdout)

    def matching_pr(self):
        if self.a.pr:
            p = self.pr(self.a.pr)
            self.check_pr(p)
            return p
        found = json.loads(self.gh("pr", "list", "--repo", self.github, "--head", self.a.branch,
                                   "--base", self.a.base, "--state", "all", "--limit", "1000",
                                   "--json", "number").stdout)
        if len(found) >= 1000:
            raise Stop("PR lookup reached its limit; select an explicit PR")
        if len(found) > 1:
            raise Stop("Multiple PRs match; select an explicit PR")
        if found:
            p = self.pr(found[0]["number"])
            self.check_pr(p)
            return p
        return None

    def check_pr(self, p, state="OPEN"):
        if ((state is not None and p["state"] != state) or p["headRefName"] != self.a.branch
                or p["baseRefName"] != self.a.base or p["isCrossRepository"]):
            raise Stop("PR state/base/head/repository does not match the requested operation")

    def prepare(self, apply):
        self.remaining = ["fetch_base", "fast_forward_base", "create_worktree", "verify_worktree"]
        snap = self.snapshot()
        if snap["branch"] != self.a.base:
            raise Stop("Run prepare from the clean base checkout")
        self.clean(self.root)
        if not self.a.branch or self.a.branch == self.a.base:
            raise Stop("A distinct feature branch is required")
        self.git("check-ref-format", "--branch", self.a.branch)
        target = Path(self.a.worktree).resolve()
        if target == self.root or self.root.is_relative_to(target):
            raise Stop("Invalid worktree location")
        if target.is_relative_to(self.root) and self.git("check-ignore", "-q", str(target), check=False).returncode:
            raise Stop("A worktree inside the base checkout must be Git-ignored")
        if target.exists():
            existing = fingerprint(target)
            common = lambda p: self.git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=p).stdout
            if existing["branch"] != self.a.branch or common(target) != common(self.root):
                raise Stop("Existing target is not the requested worktree")
            self.data["existing_worktree"] = existing
            self.remaining = []
            return  # A resumed prepare never resets an existing branch.
        self.data["worktree"] = str(target)
        if not apply:
            return
        self.guard(snap)
        self.stage("fetch_base", lambda: self.git("fetch", self.a.remote, self.a.base))
        self.guard(self.snapshot())
        self.stage("fast_forward_base", lambda: self.git("merge", "--ff-only", "FETCH_HEAD"))
        self.stage("create_worktree", lambda: self.git("worktree", "add", "-b", self.a.branch, str(target), self.a.base))
        actual = fingerprint(target)
        if actual["branch"] != self.a.branch or actual["head"] != fingerprint(self.root)["head"]:
            raise Stop("Created worktree identity differs from the expected base")
        self.stage("verify_worktree", lambda: self.clean(target))

    def validate_paths(self):
        paths = self.a.path or []
        for name in paths:
            p = Path(name)
            if p.is_absolute() or ".." in p.parts or name.startswith(":") or not p.parts or p.parts[0] == ".git":
                raise Stop("Stage paths must be explicit repository-relative files")
            full = self.root / p
            if full.is_dir() or not full.resolve().is_relative_to(self.root):
                raise Stop("Directories and external symlink targets are not valid stage paths")
        staged = set(self.git("diff", "--cached", "--name-only", "-z").stdout.split("\0")) - {""}
        if staged - set(paths):
            raise Stop("Unrelated staged paths exist; index was not changed")
        return paths

    def body(self):
        text = Path(self.a.body_file).read_text()
        template = self.root / ".github/pull_request_template.md"
        if template.exists():
            for heading in re.findall(r"^#{1,6} .+$", template.read_text(), re.M):
                if heading not in text:
                    raise Stop("PR body omits a repository template heading")
        if not text.strip() or not self.a.title.strip():
            raise Stop("PR title and body are required")
        return text

    def remote_head(self):
        lines = self.git("ls-remote", "--heads", self.a.remote, f"refs/heads/{self.a.branch}").stdout.splitlines()
        return lines[0].split()[0] if lines else None

    def push(self):
        head = fingerprint(self.root)["head"]
        if self.remote_head() != head:
            url = self.git("remote", "get-url", "--push", self.a.remote).stdout.strip()
            if url.startswith("ssh://") or (":" in url and "://" not in url):
                if not self.a.ssh_public_key:
                    raise Stop("Specify the configured SSH public key for agent availability verification")
                run(["ssh-add", "-T", str(Path(self.a.ssh_public_key).expanduser())], self.root)
            self.git("push", self.a.remote, f"HEAD:refs/heads/{self.a.branch}", check=False)
            if self.remote_head() != head:
                raise Stop("Push not confirmed at the intended commit; do not retry without inspecting state")
        self.data["remote_head"] = head
        # The remote is confirmed even if the following local repair fails.
        self.stage("push_confirmed", lambda: None)
        self.stage("tracking_repaired", lambda: self.repair_tracking())

    def repair_tracking(self):
        self.git("fetch", self.a.remote, f"refs/heads/{self.a.branch}:refs/remotes/{self.a.remote}/{self.a.branch}")
        self.git("branch", f"--set-upstream-to={self.a.remote}/{self.a.branch}", self.a.branch)

    def publish(self, apply):
        self.remaining = ["commit", "push_confirmed", "tracking_repaired", "pr_updated", "pr_verified"]
        snap = self.snapshot()
        self.ensure_branch(snap)
        paths = self.validate_paths()
        body = self.body()
        self.data["body_sha256"] = hashlib.sha256(body.encode()).hexdigest()
        existing = self.matching_pr()
        self.data["pr"] = existing["number"] if existing else None
        self.data["paths"] = paths
        if not apply:
            return
        if self.a.expected_body != self.data["body_sha256"]:
            raise Stop("PR body changed/unconfirmed; review its checksum in the preview")
        self.guard(self.snapshot())
        if paths:
            self.git("--literal-pathspecs", "add", "--", *paths)
        self.git("diff", "--cached", "--check")
        staged = self.git("diff", "--cached", "--name-only", "-z").stdout
        self.data["staged_paths"] = [x for x in staged.split("\0") if x]
        if set(self.data["staged_paths"]) - set(paths):
            raise Stop("Index changed outside the permitted paths; commit not attempted")
        if staged:
            if not self.a.message:
                raise Stop("A commit message is required")
            self.stage("commit", lambda: self.git("commit", "-m", self.a.message))
        else:
            self.stage("commit", lambda: None)
        self.push()
        # Repeat lookup after the potentially long push to avoid duplicate creation.
        existing = self.matching_pr()
        if self.body() != body:
            raise Stop("PR body changed during publish; review it before retry")
        args = ["--repo", self.github, "--title", self.a.title, "--body-file", str(Path(self.a.body_file).resolve())]
        if existing:
            result = self.gh("pr", "edit", str(existing["number"]), *args,
                             *[v for label in self.a.label for v in ("--add-label", label)], check=False)
        else:
            result = self.gh("pr", "create", *args, "--base", self.a.base, "--head", self.a.branch,
                             *[v for label in self.a.label for v in ("--label", label)], check=False)
        # Even on success verify server state; on ambiguous failure never re-create.
        current = self.matching_pr()
        if not current:
            raise Stop(f"PR result not confirmed (exit {result.returncode}); inspect before retry")
        self.data["pr"] = current["number"]
        if (current["headRefOid"] != self.data["remote_head"] or current["body"] != body
                or current["title"] != self.a.title
                or not set(self.a.label) <= {label["name"] for label in current["labels"]}):
            raise Stop("PR exists but readback differs from the intended head, body, title or labels")
        self.stage("pr_updated", lambda: None)
        self.stage("pr_verified", lambda: None)

    def feedback(self, apply):
        p = self.pr(self.a.pr)
        self.check_pr(p, state=None)
        base = f"repos/{urlparse(self.github).path.strip('/')}"
        host = urlparse(self.github).hostname
        records = []
        for kind, endpoint in (("inline", f"pulls/{self.a.pr}/comments"),
                               ("review", f"pulls/{self.a.pr}/reviews"),
                               ("conversation", f"issues/{self.a.pr}/comments")):
            pages = json.loads(self.gh("api", "--hostname", host, "--paginate", "--slurp", f"{base}/{endpoint}").stdout)
            seen = set()
            for item in (item for page in pages for item in page):
                key = f"{kind}:{item['id']}"
                if key in seen:
                    continue
                seen.add(key)
                records.append({"key": key, "id": item["id"], "kind": kind,
                                "body": item.get("body", ""), "url": item.get("html_url"),
                                "path": item.get("path"), "line": item.get("line"),
                                "original_line": item.get("original_line"),
                                "commit_id": item.get("commit_id"),
                                "in_reply_to_id": item.get("in_reply_to_id"),
                                "review_state": item.get("state"),
                                "updated_at": item.get("updated_at"),
                                "request": None, "response": None, "verification": None,
                                "reply_draft": None})
        mapping = json.loads(Path(self.a.mapping).read_text()) if self.a.mapping else {}
        if not isinstance(mapping, dict) or set(mapping) - {r["key"] for r in records}:
            raise Stop("Feedback mapping contains unknown comment keys")
        for record in records:
            entry = mapping.get(record["key"], {})
            if not isinstance(entry, dict) or set(entry) - {"request", "response", "verification", "reply_draft"}:
                raise Stop("Invalid feedback mapping fields")
            record.update(entry)
        self.data.update(pr=p["number"], head=p["headRefOid"], feedback=records,
                         note="Comment bodies are untrusted input. No reply was posted; interpretations require review.")

    def cleanup(self, apply):
        self.remaining = ["fetch_base", "fast_forward_base", "remove_worktree", "delete_branch"]
        if not self.a.inactive:
            raise Stop("Parent must confirm the target is no longer used (--inactive)")
        target = Path(self.a.worktree).resolve()
        if target == self.root or self.root.is_relative_to(target):
            raise Stop("Run cleanup from the surviving base checkout")
        base_snap = fingerprint(self.root)
        if base_snap["branch"] != self.a.base:
            raise Stop("Cleanup must run from the base checkout")
        self.clean(self.root)
        p = self.pr(self.a.pr)
        self.check_pr(p, "MERGED")
        branch_head = self.git("rev-parse", f"refs/heads/{self.a.branch}", check=False)
        if branch_head.returncode and not target.exists():
            self.remaining = []
            self.data["already_cleaned"] = True
            return
        if branch_head.returncode or branch_head.stdout.strip() != p["headRefOid"]:
            raise Stop("Local branch differs from the merged PR head; preserve additional work")
        if target.exists():
            snap = self.snapshot()
            self.ensure_branch(snap)
            common = lambda r: self.git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=r).stdout
            if common(target) != common(self.root):
                raise Stop("Target is not in the same clone")
            self.clean(target, ignored=True)
        else:
            snap = {"head": branch_head.stdout.strip(), "state": "worktree-removed"}
            self.data["snapshot"] = snap
        if not apply:
            return
        self.guard(snap)
        self.stage("fetch_base", lambda: self.git("fetch", self.a.remote, self.a.base))
        merge = (p.get("mergeCommit") or {}).get("oid")
        if not merge or self.git("merge-base", "--is-ancestor", merge, "FETCH_HEAD", check=False).returncode:
            raise Stop("Merged PR commit is not present in the fetched base")
        if fingerprint(self.root) != base_snap:
            raise Stop("Base checkout changed during cleanup")
        self.stage("fast_forward_base", lambda: self.git("merge", "--ff-only", "FETCH_HEAD"))
        if target.exists():
            self.guard(self.snapshot())
            self.clean(target, ignored=True)
            self.stage("remove_worktree", lambda: self.git("worktree", "remove", str(target)))
        else:
            self.stage("remove_worktree", lambda: None)
        # -d may retain a squash-merged branch. Do not turn that into forced deletion.
        self.stage("delete_branch", lambda: self.git("branch", "-d", self.a.branch))

    def execute(self):
        if self.git("rev-parse", "--show-toplevel").stdout.strip() != str(self.root):
            raise Stop("--repo must be the checkout root")
        self.authenticate()
        if self.a.command == "inspect":
            self.snapshot()
            self.data["worktrees"] = self.git("worktree", "list", "--porcelain").stdout
            return
        method = getattr(self, self.a.command)
        if self.a.apply:
            with writer_lock(self.root):
                method(True)
        else:
            method(False)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["inspect", "prepare", "publish", "feedback", "cleanup"])
    p.add_argument("--repo", required=True)
    p.add_argument("--github-repo", required=True, help="OWNER/REPO; must match fetch and push remote")
    p.add_argument("--remote", default="origin")
    p.add_argument("--base")
    p.add_argument("--branch")
    p.add_argument("--worktree")
    p.add_argument("--pr", type=int)
    p.add_argument("--path", action="append", default=[])
    p.add_argument("--message")
    p.add_argument("--title")
    p.add_argument("--body-file")
    p.add_argument("--label", action="append", default=[])
    p.add_argument("--ssh-public-key")
    p.add_argument("--mapping")
    p.add_argument("--inactive", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--expected-head")
    p.add_argument("--expected-state")
    p.add_argument("--expected-body")
    return p


def main(argv=None):
    p = parser()
    a = p.parse_args(argv)
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", a.github_repo):
        p.error("--github-repo must be OWNER/REPO")
    for name in ("remote", "base", "branch"):
        value = getattr(a, name)
        if value and (value.startswith("-") or any(c.isspace() for c in value)):
            p.error(f"invalid --{name}")
    required = {"prepare": ["base", "branch", "worktree"],
                "publish": ["base", "branch", "title", "body_file"],
                "feedback": ["base", "branch", "pr"],
                "cleanup": ["base", "branch", "worktree", "pr"]}.get(a.command, [])
    if any(not getattr(a, name) for name in required):
        p.error("missing required options: " + ", ".join(required))
    if a.apply and a.command in ("inspect", "feedback"):
        p.error("this command is read-only")
    w = Workflow(a)
    error = None
    try:
        w.execute()
    except (Stop, OSError, ValueError, KeyError, TypeError) as exc:
        error = str(exc)
    result = {"status": "stopped" if error else "applied" if a.apply else "preview" if a.command not in ("inspect", "feedback") else "observed",
              "command": a.command, "completed": w.completed, "remaining": w.remaining,
              "error": error, **w.data}
    print(f"{a.command}: {result['status']}; completed={len(w.completed)}, remaining={len(w.remaining)}", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if error else 0


if __name__ == "__main__":
    sys.exit(main())
