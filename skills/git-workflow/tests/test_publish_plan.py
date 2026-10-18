"""publish_planの固定schema、秘匿エラー、canonical digest契約を検証する。"""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish_plan.py"
SPEC = importlib.util.spec_from_file_location("publish_plan", SCRIPT)
publish_plan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish_plan)


def valid_plan():
    """テスト用の合成公開planを返す。"""
    return {
        "version": "workflow-plan/v1", "purpose": "synthetic", "destination": {
            "host": "github.example", "repository": "owner/repo", "remote": "origin",
            "base": "main", "branch": "codex/change",
        }, "paths": ["skills/example/SKILL.md"], "title": "Synthetic change",
        "labels": ["codex"], "operations": ["pr", "commit", "push"],
        "request": {"reference": "user request", "state": "confirmed"},
        "validation": {"state": "passed", "head": "a" * 40,
                       "snapshot_state": "b" * 64, "reference": "local checks", "reason": ""},
        "body_requirements": {"marker": "Codex", "headings": ["# Summary"], "labels": []},
    }


class PublishPlanSchema(unittest.TestCase):
    """公開planが固定schemaと値制約を満たすことを確認する。"""

    def test_valid_plan_returns_same_object(self):
        # Given
        value = valid_plan()
        # When
        result = publish_plan.validate_plan(value)
        # Then
        self.assertIs(result, value)

    def test_rejects_unknown_nested_key(self):
        # Given
        value = valid_plan()
        value["destination"]["extra"] = "private-looking-input"
        # When / Then
        with self.assertRaises(ValueError) as raised:
            publish_plan.validate_plan(value)
        self.assertNotIn("private-looking-input", str(raised.exception))

    def test_load_plan_rejects_duplicate_json_key(self):
        # Given
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plan.json"
            path.write_text('{"version":"bad","version":"private"}', encoding="utf-8")
            # When / Then
            with self.assertRaises(ValueError) as raised:
                publish_plan.load_plan(path)
        self.assertNotIn("private", str(raised.exception))

    def test_rejects_bad_field_types_including_bool(self):
        # Given
        value = valid_plan()
        value["purpose"] = True
        # When / Then
        with self.assertRaises(ValueError):
            publish_plan.validate_plan(value)

    def test_rejects_path_traversal(self):
        # Given
        value = valid_plan()
        value["paths"] = ["docs/../secret.txt"]
        # When / Then
        with self.assertRaises(ValueError):
            publish_plan.validate_plan(value)

    def test_rejects_wrong_version(self):
        # Given
        value = valid_plan()
        value["version"] = "workflow-plan/v2"
        # When / Then
        with self.assertRaises(ValueError):
            publish_plan.validate_plan(value)

    def test_validation_states_require_their_evidence(self):
        # Given
        value = valid_plan()
        value["validation"]["reference"] = ""
        # When / Then
        with self.assertRaises(ValueError):
            publish_plan.validate_plan(value)

    def test_not_required_validation_requires_reason(self):
        # Given
        value = valid_plan()
        value["validation"].update(state="not_required", reference="", reason="")
        # When / Then
        with self.assertRaises(ValueError):
            publish_plan.validate_plan(value)

    def test_canonical_digest_uses_sorted_compact_utf8_json(self):
        # Given
        value = {"z": "日本語", "a": [1, True]}
        expected = hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        # When
        result = publish_plan.canonical_digest(value)
        # Then
        self.assertEqual(expected, result)


if __name__ == "__main__":
    unittest.main()
