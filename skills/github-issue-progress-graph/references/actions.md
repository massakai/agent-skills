# GitHub Actionsによる自動更新の導入設計

この版は設計であり、実行可能workflowやAPI collector/publisherの同梱・有効化は行わない。
生成処理の共用と、自動運用の権限・排他・検証を分けて検討する。

## 推奨する導入順

1. Codexから手動で取得・生成し、図と本文差分を確認する。
2. 対象repositoryへ`workflow_dispatch`だけのpreviewを別変更で導入する。
   許可したroot・Projectを固定し、読取り専用のcollector、既存generator、Mermaid検証を接続する。
3. 実取得のページ送り・Unknown・private情報の扱いと、検証失敗時に書かないことを確認する。
4. 明示承認の対象rootだけを更新するpublisherを追加する。
5. 手動運用の成功を確認後、低頻度の`schedule`を追加する。

自然言語による毎回のAI判断を必須にせず、収集と限定更新を決定的な処理にする。
初回の図分割・配置・業務上の読み方はCodexが担当し、その後の同形式の再生成をActionsへ移す。

## 更新契機の比較

| 方式 | 利点 | 制約と用途 |
| --- | --- | --- |
| workflow_dispatch | 対象と送信内容を確認しやすい | 最初の導入に使う |
| schedule | ProjectのStatus変更や依存変更も次回取得で反映できる | 即時反映ではなく、遅延や実行漏れを考慮する |
| issuesイベント | close/reopen等へ素早く反応できる | Project field・全依存変更の網羅手段とみなさない |
| Webhook＋repository_dispatch | 外部からProject変更等を契機にできる | App・受信処理・追加認証が必要で、初版には過大 |

公式の[schedule仕様](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)ではdefault branch上で実行され、高負荷時の遅延・dropがある。
public repositoryでは無活動による停止も考慮する。
専用receiverを持たない初期案は手動実行＋定期取得を推奨する。

## 認証と配置

公式の[ProjectsとActions](https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/automating-projects-using-actions)では、repository単位の`GITHUB_TOKEN`はProjectへアクセスできない。
user-owned Projectには必要な範囲のPAT、organization-owned ProjectにはGitHub Appを候補にし、所有形態とアクセス範囲を実機確認する。
この用途でProjectへ書く権限は不要である。

Issue本文更新用のrepository tokenと、Project読取り用の認証を分離できる設計にする。
Issue更新側は`issues: write`、必要ならスクリプト取得側は`contents: read`とし、[最小権限](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)へ限定する。
collectorが別repositoryの境界Issueを読む場合は、その対象へのアクセスも明示する。
GitHub Appの登録、PAT発行・secret保存は、この設計への同意だけで実行しない。

privateな対象のジョブは、そのrepositoryまたは承認されたprivate実行場所で行う。
公開のスキルrepositoryでprivate Issueの本文・タイトル・生成画像を扱わない。
共有スキルのコードはreview済みcommitへ固定し、導入対象が管理するcollector/publisherと同じ実行版を記録する。

## 更新と検証の契約

- root・Project・配置marker・読取り対象を設定で固定し、Issue本文やタイトルから任意コマンド・更新先を作らない。
- 全ページ取得と選択Projectの同定に失敗したら、古い図を保持してジョブを失敗にする。
- 生成後にノード・native辺・状態の照合とparse/renderを実行する。
  初回、生成器・Mermaid版・レイアウト変更時は人が目視確認する。
  無人実行は事前に確認した版と形式に限定し、文字切れ等の検出限界を残す。
- rootごとのconcurrency groupで同時publisherを直列化する。
  手動担当と自動担当も同時に同じIssueを書かない。
- 最新本文と基準hashを送信直前に照合し、差分があれば候補を破棄して次回へ戻す。
  GitHub本文更新をcompare-and-swapと仮定しない。
  この照合とconcurrencyは人の同時編集を完全に排除しないため、管理範囲の運用を決める。
- 管理marker外を維持し、意味内容が不変なら日時だけを書き換えない。
- 更新後に本文と管理ブロックを読み戻す。
  タイムアウト等で成否不明なら先に読み戻し、盲目的に再送しない。
- ログは件数・検査結果・更新有無へ絞り、本文・tokenを出さない。
  preview成果物の公開範囲・保持期間も対象repositoryの方針へ合わせる。

導入前には、別repository同番号、100件超のページ、Status未設定、権限不足、循環、時刻だけの差分、手動編集との競合、更新後readback失敗を検査する。
スキルのローカル生成試験の成功を、collector/publisherやActions実行の成功と読み替えない。

## APIの正本

- [Sub-Issue REST API](https://docs.github.com/en/rest/issues/sub-issues)
- [native依存 REST API](https://docs.github.com/en/rest/issues/issue-dependencies)
- [Issue本文更新 REST API](https://docs.github.com/en/rest/issues/issues#update-an-issue)
