---
name: mermaid-validate-and-render
description: "`parse -> render -> 修正` のループを必須にして Mermaid 図を安全に作成・修正・検証する。Mermaid 図の新規作成、既存 Mermaid の修正、文法エラー対応、描画確認つきの検証が必要なときに使う。"
---

# Mermaid Validate And Render

## 目的

見た目だけもっともらしい Mermaid を完成扱いにせず、`parse` と実レンダリングの両方を通過した Mermaid だけを返す。

## このスキルを使う場面

- ユーザーが Mermaid 図の作成を依頼したとき
- 既存の Mermaid ブロックを修正したいとき
- Mermaid が parse できない、render できない、壊れやすいとき
- コミット、ドキュメント化、共有の前に Mermaid を検証したいとき

## このスキルを使わない場面

- 概念図の説明だけが必要で、Mermaid 本文は不要なとき
- 主作業が Mermaid 以外の図形式の編集で、Mermaid が本題ではないとき

## 入力

- 必須入力: 図で表したい内容、または既存の Mermaid 文字列やファイル
- 任意入力: 図の種類、出力パス、出力形式、スタイル制約

## 手順

1. 図の種類と、表現に必要な最小構成を整理する。
2. 書き方の指針が必要なら次を読む。
   - 安全な構文とガードレールは `references/authoring-rules.md`
   - 最小テンプレートは `references/diagram-patterns.md`
3. Mermaid を新規作成または修正する。
4. `node scripts/validate_mermaid.mjs <file.mmd>` を実行する。
5. `parse` に失敗したら Mermaid を修正し、成功するまで再検証する。
6. `parse` 成功後に `scripts/render_mermaid.sh <file.mmd> <output.svg>` を実行する。
7. `render` に失敗したら Mermaid を修正し、必ず `parse` からやり直す。render だけを再試行して完了扱いにしない。
8. 失敗が続く、原因が曖昧な場合は `references/common-errors.md` を読んで対処パターンを当てる。
9. `parse` と `render` の両方が成功した Mermaid だけを完了扱いにする。

## 出力

- 検証済みの Mermaid 本文
- `parse` 成功の報告
- `render` 成功の報告
- 必要なら前提や残る表現上の制約

## ガードレール

- `parse` 成功前に Mermaid を完成扱いにしない
- 実レンダリング成功前に Mermaid を完成扱いにしない
- 「たぶん動く」「見た目は正しそう」で返さない
- トリッキーな書き方より、小さく明示的な図を優先する
- 記号や曖昧さを含むラベルは `references/authoring-rules.md` の引用ルールを優先する
- インストール方法や呼び出し方を案内するときは `references/install-and-usage.md` を読む
