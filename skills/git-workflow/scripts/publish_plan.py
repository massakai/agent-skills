#!/usr/bin/env python3
"""公開用planの読み込み、schema検証、canonical digest計算を行う。"""

import hashlib
import json
from pathlib import Path
import re


class _InvalidPlan(ValueError):
    """入力値を表示せずに公開planの不正を表す。"""


def _object(pairs):
    """重複キーのないJSON objectを作成する。"""
    result = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidPlan("duplicate JSON key")
        result[key] = value
    return result


def load_plan(path):
    """UTF-8 JSONを読み込み、重複キーを拒否する。

    Args:
        path: 読み込むJSONファイルのパス。

    Returns:
        schema検証を完了したplan。

    Raises:
        ValueError: JSON構文、キー、型、値、versionのいずれかが不正な場合。
        OSError: ファイルを読み込めない場合。
    """
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_object)
    except (json.JSONDecodeError, UnicodeError, _InvalidPlan) as exc:
        raise ValueError("invalid plan JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("plan root must be an object")
    return validate_plan(value)


def canonical_digest(value):
    """canonical JSON表現のSHA-256 digestを返す。"""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError("object keys do not match schema")


def _string(value, nonempty=False):
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise ValueError("invalid string value")


def _string_list(value, unique=False, heading=False):
    if not isinstance(value, list):
        raise ValueError("expected a list")
    seen = set()
    for item in value:
        _string(item, nonempty=True)
        if heading and re.fullmatch(r"#{1,6} .+", item) is None:
            raise ValueError("invalid Markdown heading")
        if unique and item in seen:
            raise ValueError("duplicate list item")
        seen.add(item)


def _relative_file(path):
    _string(path, nonempty=True)
    if (path.startswith(("/", "\\", ":")) or "\\" in path or
            any(part in {"", ".", ".."} for part in path.split("/")) or
            ".git" in path.split("/")):
        raise ValueError("invalid relative file path")


def _domain(host):
    _string(host, nonempty=True)
    if (":" in host or "@" in host or "/" in host or "\\" in host or
            any(ch.isspace() for ch in host) or
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host) is None):
        raise ValueError("invalid host domain")


def _destination(value):
    _keys(value, ("host", "repository", "remote", "base", "branch"))
    _domain(value["host"])
    repository = value["repository"]
    _string(repository, nonempty=True)
    if re.fullmatch(r"[\w.-]+/[\w.-]+", repository, flags=re.ASCII) is None:
        raise ValueError("invalid repository name")
    for key in ("remote", "base", "branch"):
        item = value[key]
        _string(item, nonempty=True)
        if item.startswith("-") or any(ch.isspace() for ch in item):
            raise ValueError("invalid destination value")


def _validation(value):
    _keys(value, ("state", "head", "snapshot_state", "reference", "reason"))
    if not isinstance(value["state"], str) or value["state"] not in ("passed", "not_required", "unresolved"):
        raise ValueError("invalid validation state")
    if not isinstance(value["head"], str) or re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", value["head"]) is None:
        raise ValueError("invalid validation head")
    if not isinstance(value["snapshot_state"], str) or re.fullmatch(r"[0-9a-fA-F]{64}", value["snapshot_state"]) is None:
        raise ValueError("invalid validation snapshot state")
    _string(value["reference"])
    _string(value["reason"])
    if value["state"] == "passed" and not value["reference"]:
        raise ValueError("passed validation requires a reference")
    if value["state"] == "not_required" and not value["reason"]:
        raise ValueError("not_required validation requires a reason")


def validate_plan(value):
    """公開planの固定schemaと全フィールドの制約を検証する。

    Args:
        value: 検証するJSON相当の値。

    Returns:
        正常なら入力と同一のobject。

    Raises:
        ValueError: 型、キー、値、またはschema制約に違反した場合。
    """
    root_keys = ("version", "purpose", "destination", "paths", "title", "labels",
                 "operations", "request", "validation", "body_requirements")
    _keys(value, root_keys)
    if value["version"] != "workflow-plan/v1" or not isinstance(value["version"], str):
        raise ValueError("unsupported plan version")
    _string(value["purpose"], nonempty=True)
    _destination(value["destination"])
    paths = value["paths"]
    if not isinstance(paths, list):
        raise ValueError("paths must be a list")
    seen_paths = set()
    for path in paths:
        _relative_file(path)
        if path in seen_paths:
            raise ValueError("duplicate path")
        seen_paths.add(path)
    _string(value["title"], nonempty=True)
    _string_list(value["labels"], unique=True)
    operations = value["operations"]
    if not isinstance(operations, list) or any(not isinstance(x, str) for x in operations):
        raise ValueError("operations must be a string list")
    if len(set(operations)) != len(operations) or set(operations) != {"commit", "push", "pr"}:
        raise ValueError("invalid operations")
    _keys(value["request"], ("reference", "state"))
    _string(value["request"]["reference"], nonempty=True)
    if not isinstance(value["request"]["state"], str) or value["request"]["state"] not in ("confirmed", "unresolved"):
        raise ValueError("invalid request state")
    _validation(value["validation"])
    body = value["body_requirements"]
    _keys(body, ("marker", "headings", "labels"))
    _string(body["marker"], nonempty=True)
    _string_list(body["headings"], unique=True, heading=True)
    _string_list(body["labels"], unique=True)
    return value
