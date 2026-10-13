"""実GitHubへ接続せず、待機と終了後照合の合成シナリオを返す。"""

import argparse
import json
import time
from pathlib import Path


def main() -> int:
    """シナリオと実行履歴に応じた偽のgh応答を返す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        required=True,
        choices=[
            "success",
            "failure",
            "cancelled",
            "head_changed",
            "pending",
        ],
    )
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    args.state_dir.mkdir(parents=True, exist_ok=True)
    history = args.state_dir / "calls.jsonl"
    calls = (
        [json.loads(line) for line in history.read_text().splitlines()]
        if history.exists()
        else []
    )
    with history.open("a") as stream:
        stream.write(json.dumps(args.command) + "\n")
    watches = sum(call[:2] == ["run", "watch"] for call in calls)
    changed = args.scenario == "head_changed" and watches > 0
    head = "b" * 40 if changed else "a" * 40
    conclusion = {"failure": "failure", "cancelled": "cancelled"}.get(
        args.scenario, "success"
    )
    incomplete = args.scenario == "pending" and watches < 2
    action = args.command[:2]

    if action == ["run", "watch"]:
        print("合成watchの中間出力", flush=True)
        time.sleep(0.05)
        return 0 if conclusion == "success" else 1
    if action == ["pr", "view"]:
        result = {"headRefOid": head}
    elif action == ["pr", "checks"]:
        result = [
            {
                "name": "required-check",
                "state": "IN_PROGRESS" if incomplete else conclusion.upper(),
            }
        ]
    elif action == ["run", "view"]:
        result = {
            "headSha": "b" * 40 if args.command[2] == "new-run" else "a" * 40,
            "status": "completed",
            "conclusion": conclusion,
            "jobs": [{"name": "acceptance", "conclusion": conclusion}],
        }
    else:
        parser.error("run watch/viewまたはpr view/checksを指定してください")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
