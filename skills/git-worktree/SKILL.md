---
name: git-worktree
description: "作業を分離する Git worktree を、最新の default branch と明示した branch から安全に作成・確認する。PR、commit、削除判断には使わない。"
---

# Git worktree

新しい branch 作業を分離するために、Git worktree を作成・確認するときに使う。

PR、commit、worktree の削除判断、GitHub Issue/Project の更新は扱わない。

## 作成前

1. 対象リポジトリの規約を確認する。
   default branch が `main` か `master` かを確認する。
2. ユーザーが特定の ref を指定しない限り、最新化した default branch から作成する。
3. base checkout と対象 worktree の状態、既存 branch、既存 worktree を確認する。
   既存の変更・未追跡ファイル・使用中の worktree を新しい作業に流用しない。

### SSH fetch

GitHub SSH remote から fetch する場合は、実行する同じ通常ローカル経路で `ssh-add -T <公開鍵>` を優先して確認する。
利用できない場合は `ssh-add -l` で読み込み済みの鍵を確認する。

隔離経路の失敗を鍵未登録と断定せず、秘密鍵から passphrase を外す提案をしない。
`Permission denied (publickey)` の後は、agent や資格情報ストアの状態が変わるまで fetch を再試行しない。

## 作成と確認

- branch 名と worktree パスを明示する。
- 既存の branch や worktree を上書きしない。
- 作成後は、対象 path、HEAD、branch、base との関係、`git status` を確認する。
- 共有 Git ディレクトリへの書き手は一人にする。
  別の作業と競合する場合は、作成を止めて競合を解消する。

## 境界

- この skill は作成と状態確認だけを扱う。
- 削除、commit、競合解消、PR 作業は範囲外である。
- 削除を検討する場合は、tracked/untracked/ignored を含む保全確認を先に行う。
