---
name: yaml-validate-and-check
description: "`parse -> shape check -> 修正` のループを必須にして YAML を安全に作成・修正・検証する。YAML の新規作成、既存 YAML の修正、構文エラー対応、重複キー検出、利用先に合わせた形状確認が必要なときに使う。"
---

# YAML Validate And Check

## 目的

見た目だけもっともらしい YAML を完成扱いにせず、`parse` と利用先に応じた `shape check` を通過した YAML だけを返す。

## このスキルを使う場面

- ユーザーが YAML の作成を依頼したとき
- 既存の YAML を修正したいとき
- YAML が parse できない、読み込み先で壊れる、重複キーが疑わしいとき
- コミット、デプロイ、共有の前に YAML を検証したいとき

## このスキルを使わない場面

- JSON や TOML など YAML 以外が主対象のとき
- 利用先の専用フォーマット検証だけが本題で、YAML 自体の生成や修正は不要なとき

## 入力

- 必須入力: 作りたい設定内容、または既存の YAML 文字列やファイル
- 任意入力: 利用先、必須キー、スキーマ、出力パス、コメント保持の要否

## 手順

1. YAML を誰が読むかを確認する。
   - 汎用設定なら YAML としての正当性を確認する
   - GitHub Actions、Kubernetes、OpenAPI など利用先が明確なら、その利用先の必須キーや形も確認対象に含める
2. 書き方の指針が必要なら次を読む。
   - 安全な構文とガードレールは `references/authoring-rules.md`
   - よくある形は `references/yaml-patterns.md`
3. YAML を新規作成または修正する。
4. `ruby scripts/validate_yaml.rb <file.yml>` を実行する。
5. `parse` または重複キー検出に失敗したら YAML を修正し、成功するまで再検証する。
6. `parse` 成功後に、利用先に応じた `shape check` を行う。
   - 必須キーがあるなら存在を確認する
   - 期待する型があるなら mapping / sequence / scalar の対応を確認する
   - 利用先固有の validator や schema があるなら必ず追加で実行する
7. `shape check` に失敗したら YAML を修正し、必ず `parse` からやり直す。形だけ見て完了扱いにしない。
8. 失敗が続く、原因が曖昧な場合は `references/common-errors.md` を読んで対処パターンを当てる。
9. `parse` と `shape check` の両方が成功した YAML だけを完了扱いにする。

## 出力

- 検証済みの YAML 本文
- `parse` 成功の報告
- `shape check` の報告
- 必要なら利用先の前提、未実行の専用 validator、コメント保持に関する制約

## ガードレール

- `parse` 成功前に YAML を完成扱いにしない
- 重複キーを見逃したまま返さない
- 利用先が明確なのに、汎用 YAML としての通過だけで完了扱いにしない
- インデント、クォート、複数行文字列は `references/authoring-rules.md` の安全側を優先する
- コメント保持が必要な既存 YAML は、機械的な再整形を前提にしない
- 実行方法を案内するときは `references/install-and-usage.md` を読む
