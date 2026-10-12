"""run_and_waitのCLI契約を実プロセスと合成入力で検証する。"""

import json
import os
import select
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_and_wait.py"
FAKE_GH = Path(__file__).with_name("fake_gh.py")


class CommandFixture(unittest.TestCase):
    """合成コマンドの実行場所を分離する。"""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def invoke(self, *command: str) -> subprocess.CompletedProcess[str]:
        """一つの合成コマンドを完了まで実行する。"""
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--log-dir", "logs", "--", *command],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )


class RunAndWaitTest(CommandFixture):
    """一度の起動、終了結果、ログ保存、中断転送を確認する。"""

    def test_success_emits_one_json_result(self) -> None:
        result = self.invoke(sys.executable, "-c", "print('synthetic')")
        self.assertEqual(
            [json.loads(line)["status"] for line in result.stdout.splitlines()],
            ["success"],
        )

    def test_failure_preserves_nonzero_exit_code(self) -> None:
        result = self.invoke(sys.executable, "-c", "raise SystemExit(7)")
        self.assertEqual(result.returncode, 7)

    def test_missing_command_reports_start_failure(self) -> None:
        result = self.invoke(str(self.root / "missing-command"))
        self.assertEqual(json.loads(result.stdout)["status"], "start_failed")

    def test_invalid_log_directory_reports_start_failure(self) -> None:
        (self.root / "logs").write_text("synthetic")
        result = self.invoke(sys.executable, "-c", "pass")
        self.assertEqual(json.loads(result.stdout)["status"], "start_failed")

    def test_stdout_and_stderr_are_retained_in_log(self) -> None:
        result = self.invoke(
            sys.executable,
            "-c",
            "import sys; print('out'); print('err', file=sys.stderr)",
        )
        log = self.root / json.loads(result.stdout)["log_path"]
        self.assertEqual(set(log.read_text().splitlines()), {"out", "err"})

    def test_large_output_is_retained_without_pipe_deadlock(self) -> None:
        result = self.invoke(sys.executable, "-c", "print('x' * 1000000)")
        log = self.root / json.loads(result.stdout)["log_path"]
        self.assertEqual(log.stat().st_size, 1000001)

    def test_arguments_are_not_reinterpreted_by_shell(self) -> None:
        argument = "$(touch unwanted); literal value"
        result = self.invoke(
            sys.executable, "-c", "import sys; print(sys.argv[1])", argument
        )
        log = self.root / json.loads(result.stdout)["log_path"]
        self.assertEqual(log.read_text().strip(), argument)

    def test_logs_are_owner_only(self) -> None:
        result = self.invoke(sys.executable, "-c", "pass")
        log = self.root / json.loads(result.stdout)["log_path"]
        self.assertEqual(log.stat().st_mode & 0o777, 0o600)

    def test_existing_logs_are_not_overwritten(self) -> None:
        first = self.invoke(sys.executable, "-c", "print('first')")
        second = self.invoke(sys.executable, "-c", "print('second')")
        self.assertNotEqual(
            json.loads(first.stdout)["log_path"], json.loads(second.stdout)["log_path"]
        )

    def test_delayed_command_emits_nothing_before_completion(self) -> None:
        process = subprocess.Popen(
            [
                sys.executable,
                str(SCRIPT),
                "--log-dir",
                "logs",
                "--",
                sys.executable,
                "-c",
                "import time; print('progress', flush=True); time.sleep(0.4)",
            ],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            readable, _, _ = select.select(
                [process.stdout, process.stderr], [], [], 0.2
            )
            self.assertEqual(readable, [])
        finally:
            process.communicate(timeout=10)

    def test_command_is_started_once(self) -> None:
        marker = self.root / "started"
        code = "from pathlib import Path; import sys; p=Path(sys.argv[1]); p.write_text(p.read_text()+'x' if p.exists() else 'x')"
        self.invoke(sys.executable, "-c", code, str(marker))
        self.assertEqual(marker.read_text(), "x")

    def interrupt(self, signum: int) -> subprocess.CompletedProcess[str]:
        """準備完了した子へ中断を送り、終了結果を返す。"""
        # FIFOで準備完了を同期し、中断を起動前へ誤配送しない。
        cleaned = self.root / "cleaned"
        code = (
            "import os,signal,sys,time; from pathlib import Path\n"
            "def stop(signum, frame):\n"
            " time.sleep(0.05); Path(sys.argv[2]).write_text('cleaned'); sys.exit(0)\n"
            "signal.signal(signal.SIGTERM, stop)\n"
            "signal.signal(signal.SIGINT, stop)\n"
            "Path(sys.argv[1]).write_text('ready')\n"
            "time.sleep(20)\n"
        )
        fifo = self.root / "ready"
        os.mkfifo(fifo)
        ready_fd = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
        process = subprocess.Popen(
            [
                sys.executable,
                str(SCRIPT),
                "--log-dir",
                "logs",
                "--",
                sys.executable,
                "-c",
                code,
                str(fifo),
                str(cleaned),
            ],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertTrue(select.select([ready_fd], [], [], 5)[0])
            process.send_signal(signum)
            stdout, stderr = process.communicate(timeout=10)
            return subprocess.CompletedProcess([], process.returncode, stdout, stderr)
        finally:
            os.close(ready_fd)
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_interrupt_waits_for_child_cleanup(self) -> None:
        self.interrupt(signal.SIGTERM)
        self.assertTrue((self.root / "cleaned").exists())

    def test_interrupt_is_reported_even_when_child_exits_zero(self) -> None:
        result = self.interrupt(signal.SIGTERM)
        self.assertEqual(json.loads(result.stdout)["status"], "interrupted")

    def test_sigterm_returns_signal_exit_code(self) -> None:
        result = self.interrupt(signal.SIGTERM)
        self.assertEqual(result.returncode, 143)

    def test_sigint_returns_signal_exit_code(self) -> None:
        result = self.interrupt(signal.SIGINT)
        self.assertEqual(result.returncode, 130)


class FakeCiTest(CommandFixture):
    """偽CIの終了結果を実GitHubなしで保存する。"""

    def test_fake_ci_final_conclusions(self) -> None:
        for scenario, expected in [
            ("success", "success"),
            ("failure", "failed"),
            ("cancelled", "failed"),
        ]:
            with self.subTest(scenario=scenario):
                result = self.invoke(
                    sys.executable,
                    str(FAKE_GH),
                    "--scenario",
                    scenario,
                    "--state-dir",
                    str(self.root / scenario),
                    "run",
                    "watch",
                    "old-run",
                )
                self.assertEqual(json.loads(result.stdout)["status"], expected)

    def fake(self, scenario: str, *command: str) -> dict | list:
        """合成CIの終了後照合を直接実行する。"""
        result = subprocess.run(
            [
                sys.executable,
                str(FAKE_GH),
                "--scenario",
                scenario,
                "--state-dir",
                str(self.root / scenario),
                *command,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)

    def watch(self, scenario: str, run: str = "old-run") -> None:
        """合成CI監視をラッパーで一度実行する。"""
        self.invoke(
            sys.executable,
            str(FAKE_GH),
            "--scenario",
            scenario,
            "--state-dir",
            str(self.root / scenario),
            "run",
            "watch",
            run,
        )

    def test_head_changed_readback_returns_new_head(self) -> None:
        self.watch("head_changed")
        self.assertEqual(
            self.fake("head_changed", "pr", "view")["headRefOid"], "b" * 40
        )

    def test_head_changed_old_run_retains_old_sha(self) -> None:
        self.watch("head_changed")
        self.assertEqual(
            self.fake("head_changed", "run", "view", "old-run")["headSha"], "a" * 40
        )

    def test_pending_checks_remain_incomplete_after_first_watch(self) -> None:
        self.watch("pending")
        self.assertEqual(
            self.fake("pending", "pr", "checks")[0]["state"], "IN_PROGRESS"
        )

    def test_pending_checks_complete_after_second_watch(self) -> None:
        self.watch("pending")
        self.watch("pending")
        self.assertEqual(self.fake("pending", "pr", "checks")[0]["state"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
