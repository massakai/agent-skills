# PR公開前の照合

`scripts/preflight.py publish` は、公開planと既存 `workflow.py publish` のpreviewを照合する。
commit、push、PR更新、テスト、fetchは実行しない。
GitHubの読み取りは行うため、通常のローカル実行経路で認証を確認してから使用する。
レポートは公開の承認を与えず、本文の意味や秘密情報の確認は親が担当する。

## 既存publishの変更点

planの有無にかかわらず、publish previewは `publication` と `publication_sha256` を追加出力する。
applyには、従来の `--expected-head`、`--expected-state`、`--expected-body` に加えて `--expected-publication` が必要である。
古い呼び出しのJSON・終了コードは維持するが、新しい照合値を渡さないapplyはstage前に停止する。

`publication` は宛先、base・branch、PR番号、未送信commitと変更path、stage予定path、タイトル、ラベル、メッセージ、本文digest、plan digestを含む。
fetch/push URLは全文を出さず、それぞれのhashで変更を検出する。
同一repository内のbranchを対象とし、forkや複数remote URLを許可しない。
元のremote検証、状態guard、対象限定stage、本文検査、結果不明時の読み戻しを維持する。
commit後とPR更新前にも、本文・plan・remote URLを照合する。
commit後に変化を検出した場合は、そのcommitを保持して外部更新前に停止する。

未送信commitの起点は、既存リモート作業branchの先端とする。
リモート作業branchがなければ、リモートbaseの先端を起点にする。
起点のcommit objectがローカルに存在しなければ `REMOTE_OBJECT_UNAVAILABLE` で停止し、対象refを取得してpreviewを取り直す。
起点がHEADの祖先でなければ `REMOTE_DIVERGED` で停止し、自動でrebaseやforce pushをしない。
未送信commitごとの変更pathを、rename元と先を含めて明示 `--path` と照合する。
対象外commitがあれば `OUT_OF_SCOPE_COMMIT` で停止する。
今回commitする変更がなくても、未送信commitが対象pathを変更している場合は、そのpathを指定する。
すでにpush済みのcommitだけから再開する場合は、pathを空にできる。

## planの作成

planと本文は、Git除外された作業用領域など、作業状態digestに内容が入らない場所に置く。
planを未追跡・追跡済みの対象ファイルにすると、検証対象の状態を固定できないため使用しない。
Git除外ファイルも存在・名前は状態digestへ影響するため、plan・本文・ログの保存場所を先に作ってから状態を採取する。
実キー、認証情報、会話全文を保存しない。

次はschemaを示す合成例である。
HEADとsnapshot_stateのゼロ列、宛先、path、本文要件を実際の確認値へ置き換える。
ゼロ列は検証済みの値を表さない。

```json
{
  "version": "workflow-plan/v1",
  "purpose": "利用手順の説明を更新する",
  "destination": {
    "host": "github.com",
    "repository": "example-org/example-repo",
    "remote": "origin",
    "base": "main",
    "branch": "codex/update-guide"
  },
  "paths": ["guide.md"],
  "title": "利用手順の説明を更新する",
  "labels": ["codex"],
  "operations": ["commit", "push", "pr"],
  "request": {"reference": "現在の会話のPR作成依頼", "state": "confirmed"},
  "validation": {
    "state": "passed",
    "head": "0000000000000000000000000000000000000000",
    "snapshot_state": "0000000000000000000000000000000000000000000000000000000000000000",
    "reference": "作業用ログの参照",
    "reason": ""
  },
  "body_requirements": {
    "marker": "> 🤖 **作成: Codex（AI エージェント）**",
    "headings": ["## 変更内容", "## 検証"],
    "labels": ["codex"]
  }
}
```

rootと各objectは例のキーを必須とし、未知キー・重複キー・未対応versionを拒否する。
path、label、heading、operationの配列では重複を拒否する。
pathはrepository内の正規化された相対ファイル名とし、ディレクトリ、親参照、外部symlinkを許可しない。
`operations` は `commit`、`push`、`pr` の集合に限定する。
`request.state` は `confirmed` または `unresolved` とし、後者では公開前検査を通さない。
`validation.state` は `passed`、`not_required`、`unresolved` とする。
`passed` は参照、`not_required` は検証不要の理由を必須とし、いずれも対象HEADと作業状態を照合する。
検証結果や依頼の参照先を自動で読んで承認・試験成功を証明する機能はない。
確認を担当した親が実際の依頼と証拠を読み、planへ記録する。

## 実行と引き継ぎ

まず検証を完了し、Git-onlyのinspectで対象HEADとsnapshot.stateを取得する。
ログやplanなどのignoredファイルを追加した場合も、状態を採り直す。
planの内容だけを更新してもignoredファイルの内容はsnapshot.stateを変えないが、plan digestは変わる。

```text
python3 <skill>/scripts/preflight.py publish --repo <checkout> --plan <plan.json> --body-file <body.md> --message <commit-message>
```

`--message` は、後続publishへ渡す値と同一にする。
commit不要の場合は省略できる。
対象pathに未コミット変更があるのにメッセージがなければ、stage前に `COMMIT_MESSAGE_REQUIRED` で停止する。
対象が一致したら、新規レポートは `result=satisfied` と `inputs.publication_sha256` を返す。
`inputs` のsnapshot_state、body_sha256、publication_sha256と、subject.headを後続publishの各expected値へ引き継ぐ。
後続publishにも同じ `--plan`、本文、タイトル、ラベル、path、メッセージを渡す。

レポートの `schema_version` は `workflow-evidence/v1` とする。
標準出力はJSON一つ、標準エラーは短い概要であり、終了コードは一致0、不一致1、plan不正2、取得不能4とする。
入力引数不正はargparseの終了コード2で、JSON出力前に停止する。
今回の検査は待機を行わず `pending` は返さない。
成功時も、人間の依頼範囲・本文・送信予定差分を親が確認してから実行する。

applyは照合値に加えて、planと引数・本文・検証対象の対応を読み直す。
宛先、未送信commit、タイトル、ラベル、メッセージ、planなどが変わったらpreviewを取り直す。
部分成功後も新しい状態でpreviewを作り、既存CLIの `completed` と `remaining` を確認して再開する。
planの検証対象も新しいHEAD・状態へ更新し、古い証拠を引き継がない。
レポートやdigestを保存しただけで、ユーザーの承認範囲が増えることはない。

## 停止時

`PLAN_MISMATCH`、`PLAN_UNRESOLVED`、`VALIDATION_STALE`、本文・ラベル要件の不足は、不一致として返す。
認証経路を確認できない場合は `AUTH_UNVERIFIED`、実行環境を使えない場合は `ENVIRONMENT_UNAVAILABLE` とする。
その他の前提検査で確定できなかった場合は `CHECK_UNAVAILABLE` とし、ローカルの既存previewで詳細を確認する。
初版は既存previewの最初の失敗で停止するため、後続の未実行検査は確認済みとしない。
入力値や認証出力をエラーレポートへ転記しない。
自動レビューの拒否はこのCLIから推測せず、実際に拒否を受けた親が操作と理由を報告する。
拒否された操作を別の担当や別ツールで再実行しない。
