"""長時間コマンドのログを保存し、終了結果だけをJSONで返す。"""

import argparse
import json
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path


def _run(command: list[str], log_path: Path) -> tuple[str, int, int | None]:
    """子プロセスを一度だけ起動し、中断通知を転送して終了を待つ。"""
    process: subprocess.Popen[bytes] | None = None
    interrupted: int | None = None

    def forward(signum: int, _frame: object) -> None:
        nonlocal interrupted
        interrupted = signum
        if process is not None:
            try:
                os.killpg(process.pid, signum)
            except ProcessLookupError:
                pass

    previous = {
        sig: signal.signal(sig, forward) for sig in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        descriptor = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as log:
            if interrupted is not None:
                return "interrupted", -interrupted, interrupted
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
            if interrupted is not None:
                forward(interrupted, None)
            returncode = process.wait()
        if interrupted is not None or returncode < 0:
            return "interrupted", returncode, interrupted
        return ("success" if returncode == 0 else "failed"), returncode, None
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main() -> int:
    """引数を検証し、終了時のJSONと成功・失敗を表す終了コードを返す。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", required=True, type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("-- の後にコマンドと引数を指定してください")
    if os.name != "posix":
        parser.error("macOS/Linuxの非対話コマンドに対応しています")

    started = time.monotonic()
    log_path: Path | None = None
    error: str | None = None
    interrupted: int | None = None
    try:
        args.log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=args.log_dir))
        log_path = run_dir / "command.log"
        status, returncode, interrupted = _run(command, log_path)
    except OSError as exc:
        status = "start_failed"
        returncode = 127 if isinstance(exc, FileNotFoundError) else 126
        error = type(exc).__name__

    # 中断を処理したコマンドが0で終了しても、ラッパーは成功を返さない。
    exit_code = 128 - returncode if returncode < 0 else returncode
    if interrupted is not None:
        exit_code = 128 + interrupted
    log_reference = None if log_path is None else str(log_path)
    if log_path is not None and not args.log_dir.is_absolute():
        log_reference = os.path.relpath(log_path)
    print(
        json.dumps(
            {
                "status": status,
                "exit_code": exit_code,
                "returncode": returncode,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "log_path": log_reference,
                "error": error,
            },
            ensure_ascii=False,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
