---
name: worktree-status-check
description: "gh と Git の状態を使って local の git worktree を確認し、安全に削除可能、削除候補だがローカル残りあり、作業中で削除不可に分類する。"
---

# Worktree 状態確認

この skill は、ローカルの `git worktree` の状態を確認し、各 worktree が削除可能かどうかを判定したり、掃除候補のレポートを作ったりするときに使う。破壊的な cleanup や automation を行う前に、まずこの skill を使う。

cleanupの前に対象が使われていないことを確認し、PRのbase/headとマージ後の追加コミットを照合する。ignoredファイルも残りとして扱い、保全先の内容を確認して対象から退避されるまで削除可能とは分類しない。

## 対象範囲

このskillの役割は分類と報告である。削除操作は後片付けの依頼範囲を確認して別手順で行う。会話中の既存の依頼は引き継ぎ、分類だけの依頼から削除へ進まない。

このリポジトリでは GitHub と `gh` を前提にする。

## 事前確認

1. `gh auth status` で GitHub CLI の認証状態を確認する。
2. `git worktree list --porcelain` で worktree を列挙する。
3. 各 worktree はその worktree 自身のパスで確認する。
4. 安全性の判定には未追跡・Git除外ファイルも含める。
5. 現在の thread が使っている active な worktree を、自動的に削除可能と分類しない。必要ならその前提を明示する。

## 既定の stale 判定

ユーザーが閾値を指定しない場合、次の両方を満たす worktree を stale とみなす。

- ブランチ上の最新 commit が 14 日以上前
- worktree ディレクトリ自体にも、最近のローカル作業を示す更新がない

別の閾値を使うのは、ユーザーまたはリポジトリの方針で明示されている場合だけにする。

## 分類

各 worktree は、必ず次のいずれか 1 つに分類する。

### 1. 安全に削除可能

次のすべてを満たす場合は `safe_to_remove` と分類する。

- `git status --short --untracked-files=all --ignored` が空
- 未追跡・Git除外ファイルがない。退避した場合は保全先で内容を確認済み
- 関連PRのbaseが対象の既定ブランチ、headのリポジトリとブランチが対象と一致し、マージ済みのhead commitとローカル先端が一致する。またはPRを使わない作業として不要である根拠を確認できる
- 現在の作業がその worktree をまだ使っている形跡がない

典型的なシグナル:

- `gh pr list --head <branch> --state merged` は候補抽出に使う。ブランチ名だけで判断せず、対象PRのbase/head/commitを照合する
- またはブランチがすでにマージ済みで、ユーザーの作業完了も明らか

### 2. 削除候補だがローカル残りあり

worktree 自体は完了済みまたは放置気味に見えるが、ローカルに片付け前の残りがある場合は `removal_candidate_with_leftovers` と分類する。

必要条件:

- 関連 PR がデフォルトブランチへマージ済み、または既定の閾値で stale と判断できる
- かつ `git status --short --untracked-files=all --ignored` が空ではない

あわせて次のどれに当たるかを明記する。

- 追跡済みだが未コミットの変更がある
- 未追跡ファイルがある
- Git除外ファイルがあり、保存先・内容の確認が必要
- 複数種類の残りがある

この分類は「たぶん削除してよいが、その前に cleanup か人の確認が必要」という意味で使う。

### 3. 作業中で削除不可

削除すべきでない worktree は `in_progress` と分類する。

典型的なシグナル:

- PR が open
- PRのマージ後にローカル先端が変わっている、またはPRのbase/headが一致しない
- PR はまだないが、最近の commit や最近のローカル更新から active な作業が見える
- 未 push の作業があり、まだ意図を持って保持されているように見える
- 現在のユーザー作業や現在の thread がその worktree を使っている
- 完了扱いしてよいか安全に判断できない曖昧な状態

迷う場合は、削除可能側ではなく `in_progress` を優先する。

## 推奨確認項目

各 worktree について、次を集める。

1. worktree のパスとブランチ名
2. main worktree か linked worktree か
3. `git status --short --untracked-files=all --ignored`
4. 最新 local commit 日時: `git log -1 --format=%cI`
5. upstream との関係が分かる情報: `git status -sb`
6. `gh` で確認した PR の状態
7. ブランチがデフォルトブランチへマージ済みに見えるか

使いやすいコマンド例:

```sh
gh auth status
git worktree list --porcelain
git -C <path> status --short --untracked-files=all --ignored
git -C <path> status -sb
git -C <path> log -1 --format=%cI
gh pr list --head <branch> --state all --json number,state,title,headRefName,headRefOid,baseRefName,isCrossRepository,isDraft,mergedAt,url
```

必要なら `git for-each-ref` や `git branch --merged` を使って、ブランチがローカルでマージ済みかも補足確認する。

## 出力形式

カテゴリごとに 1 セクションずつ、簡潔なレポートを作る。

各 worktree には次を含める。

- path
- branch
- classification
- short reason
- follow-up action

action の表現例:

- `safe_to_remove`: `git worktree remove` で削除し、必要なら `git worktree prune` を行う
- `removal_candidate_with_leftovers`: 残りを確認し、commit・stash・破棄のいずれかを決めてから削除する
- `in_progress`: そのまま保持する

## 安全ルール

- cleanup の主手段として `rm -rf` を勧めない。
- 未追跡・Git除外ファイルを削除可否の判定に含める。更新日時が古いだけでは破棄可能と判断しない。
- `gh auth status` が失敗した場合は、PR ベースの判定が不完全であることを明記し、ローカル情報だけで補助判定する。
- PR の状態とローカルの activity が矛盾する場合は、より安全側の分類を採用し、その理由も書く。
