---
name: github-project-management
description: "GitHub Project の項目、フィールド、状態を、対象 Issue とプロジェクト設定を確認して安全に同期・更新する。"
---

# GitHub Project management

GitHub Project の項目追加、状態・カスタムフィールド更新、Issue との同期を扱う。

Issue の作業分解、実装、PR、merge は扱わない。

## 確認と計画

1. GitHub を読む前に、資格情報ストアへ到達できる通常ローカル経路で `gh auth status` を確認する。
   sandbox・隔離経路の失敗をトークン無効や認証切れと扱わない。
2. 対象 Project、対象 Issue/PR、既存 item、利用可能な field と値を読み取る。
   更新対象を明示する。
3. Project ごとの field 名、option ID、状態遷移を推測しない。
4. Issue の実際の状態と Project の表示状態が異なる場合は、どちらを更新するかと根拠を確認する。

## 更新

- item 追加、field 更新、状態更新、item 削除は、ユーザーの明示承認後だけ実行する。
- 更新後は、対象 item と field 値を読み戻す。
- Project 更新は、Issue 作成や PR merge の成功を自動的に意味しない。
  各事実を分けて報告する。

## 境界

- Issue の本文、Sub-Issue、依存関係は範囲外である。
- PR、CI、merge は範囲外である。
