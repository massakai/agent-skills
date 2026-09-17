---
name: git-pr-workflow
description: "Git worktree と GitHub PR の確認・準備・公開・フィードバック・cleanup を安全なプレビュー付きで進める。"
---

# Git と PR のワークフロー

この skill は、リポジトリの状態を確認し、ブランチ・worktree・PR の作業を段階的に進めるときに使う。作業対象と権限を明示し、外部状態を変更する操作はプレビューを確認してから実行する。

付属 CLI の詳細な引数や出力契約が必要な場合は [workflow.md](references/workflow.md) を読む。

## 共通の前提

- `--repo PATH`、`--github-repo OWNER/REPO`、`--remote origin` を対象として明示する。
- 更新系操作では `--base` と `--branch` を明示し、プレビューの `snapshot.head` と `snapshot.state` を `--expected-head` と `--expected-state` に渡す。publishでは本文の `body_sha256` も `--expected-body` に渡す。
- 変更操作はプレビューが既定であり、実行時だけ `--apply` を付ける。
- 共有 worktree または共有 Git ディレクトリに複数の書き手を置かない。
- GitHub 操作の前に `gh auth status` を確認する。SSH push の前に、pushと同じローカル実行経路で `ssh-add -T <公開鍵>` を実行する。隔離環境で `SSH_AUTH_SOCK` が欠落した結果を鍵未登録と判定せず、その経路ではpushしない。
- `--apply` は共通Gitディレクトリに`skill-workflow.lock`を作る。隔離環境ではロック作成が拒否され得るため、更新操作は共通Gitディレクトリへ書込み可能なローカル実行経路で行う。

## 操作の境界

- `inspect` は Git と worktree の snapshot を集める読み取り専用操作である。PR 情報は返さない。
- `prepare` は指定した branch/worktree の作成または準備をプレビューし、基準ブランチの先端と作業対象を確認する。
- `publish` は明示されたパス、コミットメッセージ、PR 内容だけを対象にする。パスとラベルは繰り返し指定でき、既存PRは自動照合する。実行前に対象差分・必要なテスト・テンプレートの内容を確認する。CLIはテスト実行や本文の意味の評価を代行しない。
- `feedback` は指定 PR の状態を読み、任意の mapping JSON に従って構造化されたコメント記録を生成する。コメント送信や merge は別の明示的な承認が必要である。
- `cleanup` は、親が利用中でないことを確認し、後片付けの依頼範囲に含まれる対象を扱う。未追跡または ignored ファイルが一つでも残る場合は原則として削除せず、存続するチェックアウトの保存先へ退避し、内容を検証してから再実行する。例外は、Git除外を確認した許可リスト内の再生成可能キャッシュと、symlinkではない任意の階層の`__pycache__/`ディレクトリだけで、利用者が`--discard-generated-caches`を明示した場合である。`uv.lock`、`data/`、`logs/`、`artifacts/`はこの例外に含めない。ブランチ削除は `git branch -d` だけを使い、強制削除しない。

独立した補助作業を親の別作業と並行できる場合はサブエージェントへ委任する。導入済みなら `cost-aware-delegation` を参照する。利用できない場合は、定型作業に `gpt-5.6-luna / low` を明示し、操作範囲と完了条件を限定して渡す。共通Git領域への更新担当は一人にする。

PR の merge 後でも、base/head、merge 後の追加コミット、ローカルの未追跡・ignored ファイルを確認する。push 状態が不明な場合は推測で再実行しない。
