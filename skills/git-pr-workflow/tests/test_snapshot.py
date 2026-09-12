import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "workflow_snapshot", Path(__file__).resolve().parents[1] / "scripts/workflow.py"
)
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


class SnapshotOutput(unittest.TestCase):
    def test_ignored_files_affect_digest_without_flooding_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
            git("init", "-b", "main")
            git("config", "user.name", "Example")
            git("config", "user.email", "example@example.invalid")
            (root / ".gitignore").write_text("cache/\n")
            git("add", ".gitignore")
            git("commit", "-m", "Initial")
            (root / "cache").mkdir()
            before = workflow.fingerprint(root)
            for i in range(100):
                (root / "cache" / f"cached-file-{i}.txt").write_text("data")
            after = workflow.fingerprint(root)
            self.assertNotEqual(before["state"], after["state"])
            self.assertEqual("!! cache/", after["status"])
            self.assertFalse(after["status_truncated"])


if __name__ == "__main__":
    unittest.main()
