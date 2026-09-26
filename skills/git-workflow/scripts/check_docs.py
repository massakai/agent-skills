#!/usr/bin/env python3
"""Markdownのローカルリンク・見出しと外部ローカル参照を検査する。

インラインリンク・画像、参照リンク、ATX・Setext見出し、HTMLのIDに対応する。
コード例の実行やURLの取得は行わない。制約はreferences/workflow.mdを参照する。
"""
import argparse
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import unquote, urlsplit


def prose(text):
    """フェンスで囲まれたコードを空行に置き換えたMarkdown文字列を返す。

    Args:
        text: 検査対象のMarkdown文字列。

    Returns:
        コード例をリンク・見出しとして解釈しないための、行数を保持した本文。
    """
    result = []
    fence = None
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if match:
            mark = match[1]
            if fence is None:
                fence = mark
            elif mark[0] == fence[0] and len(mark) >= len(fence):
                fence = None
            result.append("")
        else:
            result.append(line if fence is None else "")
    return "\n".join(result)


def anchors(text):
    """Markdown見出しとHTMLのIDから参照可能なアンカーの集合を求める。

    Args:
        text: 参照先のMarkdown文字列。

    Returns:
        アンカー文字列の集合。同名見出しには出現順の番号を付ける。
        フェンス内の見出しは含めない。
    """
    text = prose(text)
    result = set(re.findall(r"\b(?:id|name)=[\"']([^\"']+)[\"']", text))
    used = set()
    lines = text.splitlines()
    for i, line in enumerate(lines):
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)(?:\s+#+\s*)?$", line)
        heading = match[1] if match else (lines[i - 1] if i and re.fullmatch(r"\s{0,3}(?:=+|-+)\s*", line) else None)
        if heading is None:
            continue
        heading = re.sub(r"<[^>]*>", "", heading)
        heading = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", heading)
        base = "".join(c for c in heading.lower() if c in "-_ " or unicodedata.category(c)[0] not in "PS").replace(" ", "-")
        slug, suffix = base, 0
        while slug in used:
            suffix += 1
            slug = f"{base}-{suffix}"
        used.add(slug)
        result.add(slug)
    return result


def check(root, names):
    """対象文書のリンク・アンカー・外部ローカル参照を読み取り専用で検査する。

    Args:
        root: リポジトリのルートを表す文字列またはPath。
        names: 検査する文書のリポジトリ相対パスのリスト。

    Returns:
        検査ファイル数・リンク数、検出した問題のリスト、検査範囲の制約を持つ辞書。
        外部URLには接続せず、代表的なローカルパスはコード例も含めて検査する。

    Raises:
        OSError: 文書の読み込みに失敗した場合。
        UnicodeError: 文書を文字列として復号できない場合。
        ValueError: URLを解析できない場合。
    """
    root = Path(root).resolve()
    errors, checked = [], 0
    for name in names:
        f = root / name
        if not f.resolve().is_relative_to(root) or not f.is_file():
            errors.append({"file": name, "reason": "source missing or outside repository"})
            continue
        text = f.read_text()
        for n, line in enumerate(text.splitlines(), 1):
            if re.search(r"file://|(?<![\w/])/(?:Users|home|private|tmp|var/folders)/|[A-Za-z]:\\", line):
                errors.append({"file": name, "line": n, "reason": "machine-specific local path (including examples)"})
            for relative in re.findall(r"`((?:\.\./)+[^`\s]+)`", line):
                if not (f.parent / relative).resolve().is_relative_to(root):
                    errors.append({"file": name, "line": n, "reason": "external relative path in example"})
        body = prose(text)
        definitions = {k.strip().casefold(): v for k, v in re.findall(r"^\s{0,3}\[([^\]]+)\]:\s*<?([^\s>]+)>?", body, re.M)}
        links = re.findall(r"\]\(\s*(<[^>]+>|(?:[^\s()]|\([^()]*\))+)\s*(?:[\"'][^\n]*?[\"']\s*)?\)", body)
        links = [v[1:-1] if v.startswith("<") else v for v in links]
        for label, ref in re.findall(r"\[([^\]]+)\]\[([^\]]*)\]", body):
            key = (ref or label).strip().casefold()
            if key not in definitions:
                errors.append({"file": name, "reason": f"undefined reference: {key}"})
            else:
                links.append(definitions[key])
        # 短縮形式の参照リンクも検査するため、定義された参照先を含める。
        links.extend(definitions.values())
        for link in links:
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc:
                continue
            target = (f.parent / unquote(parsed.path)).resolve() if parsed.path else f.resolve()
            checked += 1
            if not target.is_relative_to(root) or not target.exists():
                errors.append({"file": name, "target": link, "reason": "missing or external target"})
            elif parsed.fragment and target.suffix.lower() == ".md" and unquote(parsed.fragment) not in anchors(target.read_text()):
                errors.append({"file": name, "target": link, "reason": "missing Markdown anchor"})
    return {"files_checked": len(names), "links_checked": checked, "errors": errors,
            "limits": "No network, MDX, generated anchors, HTML href/src, or arbitrary shell-example interpretation; inspect these manually."}


def main():
    """CLI引数の文書を検査し、JSON出力とエラー有無を返す。

    Returns:
        問題があればTrue、なければFalse。プロセスの終了コードとして使う。
        検査結果は標準出力へ書き出す。

    Raises:
        SystemExit: ヘルプ表示または不正な引数で終了する場合。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--path", action="append", required=True)
    args = parser.parse_args()
    try:
        result = check(args.repo, args.path)
    except (OSError, UnicodeError, ValueError) as exc:
        result = {"errors": [{"reason": str(exc)}]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return bool(result["errors"])


if __name__ == "__main__":
    sys.exit(main())
