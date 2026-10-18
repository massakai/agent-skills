#!/usr/bin/env python3
"""公開planと実際の送信予定を読み取り専用で照合する。

Python 3.10以降、Git、通常のローカル経路で認証できるghを使用する。
レポートは操作への承認を表さず、commit・push・PR更新を実行しない。
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import publish_plan
import workflow


def publish_args(root, plan, body_file):
    """検証済みplanから既存publishのpreview用引数を作る。

    Args:
        root: 対象checkoutのルート。
        plan: schema検証済みのplan。
        body_file: 本文ファイルの明示パス。

    Returns:
        applyを無効とした既存CLIのNamespace。
    """
    destination = plan["destination"]
    args = workflow.parser().parse_args(["publish", "--repo", str(root)])
    # planの値をCLIとして再解釈しない。先頭がハイフンのタイトル等も値として扱う。
    args.github_repo = destination["repository"]
    for name in ("remote", "base", "branch"):
        setattr(args, name, destination[name])
    args.title = plan["title"]
    args.body_file = str(body_file)
    args.path = plan["paths"]
    args.label = plan["labels"]
    return args


def inspect_publish(root, plan_file, body_file, message, factory=workflow.Workflow):
    """公開予定を収集し、標準結果と終了コードを返す。

    Args:
        root: 対象checkoutのルート。
        plan_file: ローカルplanファイルのパス。
        body_file: PR本文ファイルのパス。
        message: 今回commitする場合のメッセージ。commit不要ならNone。
        factory: 既存ワークフローの生成関数。テスト時は合成境界を渡す。

    Returns:
        workflow-evidence/v1の辞書と、0・1・2・4の終了コードの組。
        この検査は待機しないためpendingは返さない。
    """
    report = {"schema_version": "workflow-evidence/v1", "kind": "publish",
              "observed_at": datetime.now(timezone.utc).isoformat(),
              "result": "unavailable", "subject": {}, "inputs": {}, "findings": [],
              "limits": ["Human authorization, body semantics and secret review remain with the parent.",
                         "Validation and request references are parent assertions, not verified approval.",
                         "No tests, fetch, commit, push or PR update are executed."]}
    code, state, exit_code = "CHECK_UNAVAILABLE", "unavailable", 4
    worker = None
    phase = "plan"
    try:
        plan = publish_plan.load_plan(plan_file)
        report["inputs"]["plan_sha256"] = publish_plan.canonical_digest(plan)
        report["subject"] = dict(plan["destination"])
        phase = "collection"
        args = publish_args(root, plan, body_file)
        args.plan = str(plan_file)
        args.message = message
        worker = factory(args)
        worker.execute()
        report["subject"] = {"destination": worker.github, "base": args.base,
                             "branch": args.branch, "head": worker.data["snapshot"]["head"]}
        report["inputs"].update({"body_sha256": worker.data["body_sha256"],
                                 "snapshot_state": worker.data["snapshot"]["state"],
                                 "publication_sha256": worker.data["publication_sha256"]})
        report["publication"] = worker.data["publication"]
        code, state, exit_code = "PUBLICATION_MATCHED", "satisfied", 0
    except ValueError:
        if phase == "plan":
            code, state, exit_code = "INVALID_PLAN", "violated", 2
        else:
            code = "CHECK_UNAVAILABLE"
    except (KeyError, TypeError):
        code = "CHECK_UNAVAILABLE"
    except (OSError, workflow.Stop) as exc:
        # コマンドの出力や入力値を出さず、定義済みの理由だけを保持する。
        known = {"PLAN_MISMATCH", "PLAN_UNRESOLVED", "VALIDATION_STALE", "BODY_REQUIREMENT_MISSING",
                 "LABEL_REQUIREMENT_MISSING", "OUT_OF_SCOPE_COMMIT", "REMOTE_DIVERGED", "COMMIT_MESSAGE_REQUIRED"}
        reason = str(exc).split(":", 1)[0]
        if reason in known:
            code, state, exit_code = reason, "violated", 1
        elif isinstance(exc, OSError):
            code = "ENVIRONMENT_UNAVAILABLE"
        elif str(exc).startswith("gh auth failed"):
            code = "AUTH_UNVERIFIED"
        elif reason in {"REMOTE_OBJECT_UNAVAILABLE", "BASE_UNAVAILABLE", "REMOTE_AMBIGUOUS"}:
            code = reason
    if worker is not None and "snapshot" in worker.data:
        report["subject"].setdefault("head", worker.data["snapshot"]["head"])
        report["inputs"].setdefault("snapshot_state", worker.data["snapshot"]["state"])
    if exit_code:
        report["limits"].append("The existing preview stops at its first failed check; later checks remain unverified.")
    report["result"] = "satisfied" if exit_code == 0 else "blocked" if exit_code in (1, 2) else "unavailable"
    report["findings"].append({"code": code, "check_id": "publication", "state": state,
                               "evidence": "See local preview and the named input files.",
                               "next_action": "Review the exact operation against the human request." if exit_code == 0
                               else "Resolve the finding and obtain a new preview; do not retry publication automatically."})
    return report, exit_code


def main(argv=None):
    """公開preflightを実行し、JSON一つと概要を出力する。

    Returns:
        検査成功は0、不一致は1、入力不正は2、取得不能は4。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["publish"])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--body-file", required=True)
    parser.add_argument("--message")
    args = parser.parse_args(argv)
    result, code = inspect_publish(Path(args.repo).resolve(), args.plan, args.body_file, args.message)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"publish preflight: {result['result']}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
