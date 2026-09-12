# 共有スキル

このディレクトリには、公開可能な AI エージェント向けスキルを配置します。

## 規約

- 1 スキル 1 ディレクトリ
- 各スキルディレクトリには `SKILL.md` を必ず置く
- 参照資料、プロンプト、補助アセットも公開可能ならスキルの近くに置く
- ディレクトリ名は `repo-orientation` や `release-checklist` のように目的が分かる名前にする

## 推奨構成

```text
skills/
  my-skill/
    SKILL.md
    references/
    examples/
```

## ここに置くもの

- 再利用できるワークフロー
- リポジトリ非依存のチェックリスト
- プロンプトのひな型
- 公開用サンプル

Git と PR の操作では、[git-pr-workflow](git-pr-workflow/SKILL.md) と [worktree-status-check](worktree-status-check/SKILL.md) を使って対象・状態・削除条件を確認する。複数エージェントへ分担するときは [cost-aware-delegation](cost-aware-delegation/SKILL.md) を使い、担当範囲と共有書き込みの責任者を明示する。

## ここに置かないもの

- 秘密情報
- 個人的なメモ
- ローカルの絶対パス
- セッションログ
- 端末固有の実行状態
