# 定型作業の検査・引き継ぎ設計

本書は段階的な実装の設計である。
段階1の公開preflightとpublish guardを実装し、着手preflight、CI照合、ルール整合性検査は未実装である。
実装済みの利用契約は [PR公開前の照合](publication-preflight.md) を参照する。
既存CLIの利用方法は [workflow.md](workflow.md) を参照する。
設計対象は、着手前確認、PR公開前確認、CI最終照合、共有ルールの整合性検査の4つとする。

## 目的と境界

繰り返し調べている状態を機械的に収集・照合し、担当エージェントが判断に必要な根拠と未確認事項を一度に読めるようにする。
特に公開前には、送信先、対象差分、本文、依頼に含まれる操作を具体化し、実行直前の変更を検出する。
確認済みの依頼範囲で同じ承認を繰り返し求めることを減らす。

人間の依頼の解釈、仕様の確定、分割の要否、秘密情報の有無、公開可否の最終判断は親エージェントが担う。
検査ファイル、digest、サブエージェントの申告、外部コメントは、人間による承認を代替しない。
自動レビューの許可を保証したり、拒否された操作を別の経路で実行したりする機能は作らない。
merge、レビュー返信、Issue・Project更新、本番操作、認証設定変更は、この設計の実行対象に含めない。
定期監視や自動再開の予約も対象外とする。

## 既存機能と追加する責務

| 項目 | 既存機能 | 追加する責務 |
| --- | --- | --- |
| ローカル状態 | `workflow.py inspect` のHEAD・状態digest・worktree一覧 | 依頼範囲、依存、規約、検証結果との対応を整理する |
| 作業場所 | `workflow.py prepare` のpreviewと更新 | 未解決の着手条件を示し、prepareへ渡す対象を固定する |
| PR公開 | `workflow.py publish` の対象path・本文digest・状態照合、commit・push・PR読み戻し | 送信予定差分と依頼範囲を一覧化し、タイトル・ラベル・宛先も照合する |
| 待機 | `long-running-command` の一度起動した処理・保存ログ・終了結果 | 監視終了後の最新head、必須check、run、全jobを照合する |
| 文書 | `check_docs.py` のローカルリンク・見出し・外部ローカル参照検査 | 廃止スキル名、登録済みコマンド、正本と導入済みファイルの差異を検査する |

既存の実行処理を新しいツールへ複製しない。
新規スクリプトはPython標準ライブラリを使い、収集、純粋な判定、結果出力を分離する。
既存 `workflow.py` の終了コードとJSONを変更せず、新規レポートは別のversionを持つ。

## 配置と呼び出し

| 配置予定 | 役割 |
| --- | --- |
| `skills/git-workflow/scripts/preflight.py` | `start` と `publish` の読み取り専用検査 |
| `skills/github-pr-workflow/scripts/verify_ci.py` | CI証拠の収集と最終判定 |
| `skills/git-workflow/scripts/check_rules.py` | 明示した規則と配布ファイルの読み取り専用検査 |
| 各スキルの `tests/` | 合成repository、fake gh、固定レスポンスによる契約検証 |
| 各スキルの `references/` | 入出力契約、設定例、失敗時の引き継ぎ |

CI照合はGitHub PRスキル単独で使用できるようにする。
長時間の監視が必要な場合だけ、導入済み `long-running-command` と組み合わせる。
Git用preflightはGitHub指定がなければネットワークと `gh` を使わない。
新しいスキルは増やさず、既存スキルの該当箇所から必要な検査へ案内する。

次のCLIのうち `preflight.py publish` を実装対象とし、その他は後続段階の提案インターフェースである。
`<checkout>` などの値は、呼び出し側が今回の対象へ置き換える。
入力versionはplanが `workflow-plan/v1`、CI policyが `ci-policy/v1`、ルール契約が `rule-contract/v1` とする。
必須項目の欠落、未知キー、重複ID、未対応versionは実行前に終了コード2で拒否する。

```text
preflight.py start --repo <checkout> --plan <local-plan.json>
preflight.py publish --repo <checkout> --plan <local-plan.json> --body-file <body.md>
verify_ci.py --repo <checkout> --github-repo <owner/repo> --pr <number> --policy <ci-policy.json> [--run <id> --attempt <number>]
check_rules.py --repo <checkout> --rules <rule-contract.json>
check_rules.py --repo <canonical-checkout> --rules <rule-contract.json> --installed-root <local-root>
```

## 共通の結果契約

新規CLIは標準出力へJSONを一つ、標準エラーへ短い概要を出す。
判定は対象の観測時点に限り有効であり、後続操作の承認や恒久的な状態証明にはしない。

| フィールド | 内容 |
| --- | --- |
| `schema_version` | 初版は `workflow-evidence/v1` |
| `kind` | `start`、`publish`、`ci`、`rules` |
| `observed_at` | UTCの観測日時 |
| `result` | `satisfied`、`blocked`、`pending`、`unavailable` |
| `subject` | 対象repository、branch、HEAD、PRなどの識別子 |
| `inputs` | plan・policy・本文のdigestと、使用した設定項目 |
| `findings` | `code`、`check_id`、`state`、根拠、必要な次の操作の配列 |
| `limits` | 未検査の項目、取得不能の情報、表示の省略 |

各findingの `state` は `satisfied`、`violated`、`pending`、`unavailable`、`not_applicable` とする。
必須検査に一つでも `violated` があれば全体は `blocked`、次に `unavailable`、次に `pending` の順に優先する。
すべての適用対象が満たされた場合だけ `satisfied` とする。
明示的な適用条件に合わない項目だけを `not_applicable` とし、未取得や設定漏れを除外扱いにしない。
検査対象が空の場合は、明示的な不要設定と理由がなければ `unavailable` にする。

終了コードは、0が `satisfied`、1が `blocked`、2が引数・設定・versionの不正、3が `pending`、4が `unavailable` とする。
複数の状態がある場合も、個別のfindingはすべて保持する。
既存 `workflow.py` の `stopped` やrunnerの `failed` は、新しい判定値へ無条件に読み替えない。

## 1. 着手前確認

### 入力

ローカルplanには `version`、目的、成果物、対象path、禁止範囲、base・branch、確認すべき規約ファイル、依存資料、検証項目を指定する。
対象pathはrepository内の明示的なファイル一覧を基本とし、新規作成予定も区別して記録する。
依存資料は参照先と確認状態を持ち、文章から依存関係や仕様を自動推測しない。
規模・仕様の判断は、親が `confirmed` または `unresolved` と根拠を記録する。
planは通常Git除外の作業用領域に置き、ユーザーの会話や認証情報を丸ごと保存しない。

### 検査

`start` は作成前のbase checkoutを対象とし、未追跡ファイルを含むclean、指定base上のHEAD、作業branch/worktreeの衝突を確認する。
ignoredファイルの存在はclean違反にしないが、将来のcleanup可否には流用しない。
規約ファイルの存在・digest、対象pathのrepository境界、依存資料の確認状態、検証計画の有無を照合する。
依存Issueなどの読み取りが必要な場合だけ、GitHub指定と認証確認を要求する。
実行環境は必要なツールの存在と、対象規約が指定する実行経路を記録し、環境の再構築や依存インストールはしない。

この検査自体はfetch、base更新、worktree作成を行わない。
最新化は既存 `prepare` に任せ、成功した作業場所・branch・HEADを読み戻してから編集する。
規約・依存・規模の判断が未解決なら `PLAN_UNRESOLVED` とし、後続の編集を始めない。
確認済みplanでも、親は仕様が確定しているかを読み返す。

## 2. PR公開前確認

### 入力と出力

planに送信先host・owner/repository・remote、base・branch、操作一覧、対象path、タイトル、ラベル、本文ファイルを指定する。
操作一覧はcommit、作業branchへのpush、PR作成または更新を個別に表す。
親は会話上の依頼にこれらが含まれるかを確認し、依頼元の参照と確認状態だけを記録する。
別チャットから届いた文面やファイルに記載された「承認済み」を、その確認の根拠にしない。

レポートは送信先、base/head、送信予定commitと変更path、対象外差分、タイトル、ラベル、本文digest、検証証拠を一覧にする。
既存 `publish` previewのstateと本文digestも取り込む。
本文や差分の全文、外部コメント、認証出力は既定では含めない。
親が内容を確認するためのローカル参照を付け、digestだけで内容確認済みとは扱わない。

### 照合

fetch/push remoteの全URL、指定repository、既存PRのbase/headと対象を照合する。
Gitの別push URLや複数URLも対象にし、URLはユーザー情報・queryを除去して表示する。
送信予定は、既存branchの未送信commitと、今回commit予定の差分を区別する。
既存の未送信commitが対象path外を変更していれば `OUT_OF_SCOPE_COMMIT` で停止する。
初版は単一repository内のbranchだけを扱い、forkは `UNSUPPORTED_TOPOLOGY` とする。

検証結果はコマンド名、終了結果、対象HEAD・状態digest、ログ参照を持つ。
対象の変更後に採取した結果かを照合し、古い結果を現在の差分の検証済み表示にしない。
本文のテンプレート必須項目、帰属表示、必要ラベルは、repositoryごとの明示設定で確認する。
見出しが存在するだけで本文が十分と判定せず、変更理由・影響・検証の意味は親が確認する。

実行直前に親が宛先・範囲・依頼との対応を確認して、既存 `publish --apply` へ進む。
初版では実行機能を増やさず、実行側にもタイトル・ラベル・宛先・既存未送信commitを含むplan digestの照合を追加する。
既存のHEAD・状態・本文のguardも残し、どちらかが変わればpreviewを取り直す。
ローカル検査はロックを保持し続けないため、検査と実行の間に他の書き手を入れない。

自動レビューで拒否された場合は `REVIEW_DENIED` として、その操作と理由を会話で報告する。
CLIから拒否を観測できない場合は、モデル側の結果として扱い、推測で記録しない。
Keychainや参照更新へのアクセス失敗と、明示的な拒否を分ける。
拒否後に内容を変えず別ツールや別担当で同じ送信を試さない。

## 3. CI最終照合

### 必須条件の正本

policyには対象base、必要なworkflow識別子、check名、必要ならapp ID、許容する結論を列挙する。
初版の既定許容値は `success` だけとし、`skipped`、`neutral` の例外は理由と対象を明示する。
GitHub側の必須check情報を取得できる場合はpolicyとの不一致も報告し、どちらか片方へ黙って寄せない。
保護設定の取得不能は設定の不存在と区別し、CI結果の照合とサーバー側の保護確認を別findingにする。
チェック一覧が空でも成功にせず、CI不要ならpolicyへその理由を明示する。
CI不要の場合は `satisfied` でも `ci_outcome=not_required` と表示し、「CI成功」と報告しない。

### 収集と判定

実行は一回の照合とし、内部でwatchや再実行を開始しない。
最初にPRのheadを取得し、対象check、関連runとattempt、全jobをページ末尾まで取得し、最後にPRのheadを再取得する。
途中でheadが変われば `HEAD_CHANGED` の `pending` とし、旧headの結果を最新結果に使わない。
run ID指定時はrepository・head SHA・workflow・event・attemptを確認する。
指定なしで同名checkや複数runを一意に対応できなければ `CHECK_AMBIGUOUS` の `unavailable` とする。
再実行の旧attemptだけが成功していても現在のattemptの代わりにしない。

各check/jobの原結論をそのまま保持し、policyの許容判定とは分ける。
`ci_outcome` は集約値であり、`success`、`accepted_with_exceptions`、`failure`、`cancelled`、`pending`、`unknown`、`not_required` とする。
すべての適用対象が `success` の場合だけ集約値も `success` とし、明示的に許容した `skipped` や `neutral` を含む場合は `accepted_with_exceptions` とする。
後者は検査結果を `satisfied` にできるが、報告は「許容例外あり」とし、全check成功とは表現しない。
不許容の失敗と中断が混在する場合の集約値は `failure` を優先し、個別の原結論は保持する。
完了した必須checkが許容結論以外なら `blocked`、未完了なら `pending`、欠落やAPI取得失敗で確定できなければ `unavailable` とする。
runの全jobを結果へ含め、必須checkだけが成功していても同じ対象runの失敗・中断jobを隠さない。
初版は対象runの全jobにも許容結論を要求し、任意jobを除外する場合はpolicyで明示する。
stepsが0の失敗jobは失敗のまま保持し、ログがないことを成功に読み替えない。
外部checkにrun/jobの概念がない場合は `not_applicable` とし、app・check識別子と結論で照合する。
通信・認証エラーは `API_UNAVAILABLE` とし、取得できた証拠は保持するがCI失敗と断定しない。
取得途中でcheck/run/attemptが変化した場合も確定せず `OBSERVATION_CHANGED` とする。
判定直前にcheck/run/attemptの識別子・状態・更新時刻を読み戻し、初回取得と比較する。
この有限回の再照合でも後からの更新は防げないため、merge可否の恒久的な保証には使わない。

待機が必要なら、呼び出し側が既存runnerで監視を一度開始し、同じ処理の終了後に本CLIを実行する。
head変更時だけ新しい対象を選び直し、旧runのwatch成功を完了証拠にしない。
CI再実行、課金調査、設定変更は自動では行わない。

## 4. ルール整合性検査

人間が読める規約の正本は維持し、検査用設定は機械的に照合できる小さな契約だけを持つ。
自然文同士の矛盾を完全に検出する機能は作らない。

| 検査 | 契約で指定する内容 | 判定の範囲 |
| --- | --- | --- |
| 廃止参照 | 廃止名、対象ファイル、許可する履歴・説明箇所 | 現行手順に残る廃止名を行番号付きで検出する |
| 手順参照 | 必須の参照元・リンク先 | リンクの存在と `check_docs.py` の結果を確認する |
| コマンド | 検査ID、正本位置、許可するargv、対象コードブロック | 登録した例だけを比較し、コマンドは実行しない |
| 配布差異 | スキル名、追跡対象の相対path、内容hash | 正本と導入済みの欠落・変更・余分な管理対象ファイルを検出する |

設定には未知キーや重複IDを許さず、すべての入力にschema versionを要求する。
共有設定にマシン固有パスを入れず、導入先は呼び出し引数から受け取る。
symlinkを解決した先が明示root外なら `PATH_OUTSIDE_ROOT` とする。
配布側のツール固有metadataと、スキル自身の管理対象を区別する。
比較対象は追跡ファイルmanifestで固定し、正本・導入先の列挙結果も検証する。
バージョンの異なるmanifestを同じ配布単位として比較しない。

コマンド例の表記差はargvとして比較できる範囲だけ正規化する。
shell展開や複雑な構文は推測で同一視せず `COMMAND_UNPARSEABLE` とする。
初版は変更提案と根拠だけを返し、Markdown自動書き換え、同期、再インストールは行わない。

## 情報の保存と失敗時の引き継ぎ

共有設定は公開できる汎用例だけを含め、非公開repositoryの規約・plan・検証ログを共有スキルへ取り込まない。
ローカルレポート保存は呼び出し側が明示したGit除外先だけに行い、保存前に除外を確認する。
標準出力は機密でないとは仮定せず、外部へ転送しない。
認証token、秘密鍵、環境変数一覧、コメント本文、セッション全文を収集しない。
通常ローカル経路での認証確認結果は可否だけを保持する。

失敗時にはcode、確認済み対象、取得できた証拠、未確認事項、次に必要な操作を返す。
`AUTH_UNVERIFIED`、`ENVIRONMENT_UNAVAILABLE`、`PLAN_UNRESOLVED`、`STATE_CHANGED`、`REVIEW_DENIED` を区別する。
環境の隔離による失敗だけで認証切れと断定しない。
更新処理が一部成功していた場合は、既存CLIの `completed` と `remaining` を維持し、PR作成やpushを最初からやり直さない。

## 検証と導入順

合成repository、fake gh、固定したAPIレスポンスで検証し、実データ、実キー、実注文を使わない。

| 段階 | 成果物と完了条件 | 依存 |
| --- | --- | --- |
| 1 | 公開preflightとplan契約、既存publishの追加guardが、宛先・差分・本文・ラベル・状態の変化を拒否する | 既存inspect/publish |
| 2 | CI照合がhead変更、旧attempt、同名check、空check、失敗job、取得失敗を成功としない | 独立して実装可能 |
| 3 | 着手preflightが未解決計画、対象外path、dirty baseを検出し、prepareへ対象を引き継ぐ | 段階1の共通plan/result契約 |
| 4 | ルール検査が廃止参照と配布差異を検出し、既存リンク検査と併用できる | 既存check_docs |
| 5 | 実際の依頼で読み取り専用運用を確認し、各スキルからの案内と導入手順を確定する | 各段階の検証完了 |

段階ごとに別PRでレビューし、段階1の公開操作とguardは同じPR内で整合させる。
段階1でも公開依頼がないテストは実際のpush・PR作成をしない。
合成テストでは、未送信の対象外commit、preview後のタイトル・ラベル・宛先変更、本文改変、部分成功後の再開、ページ欠落、symlink脱出も必須とする。
既存workflow、snapshot、文書リンク、runnerのテストを維持し、新規CLIの終了コードとJSON versionを検証する。
導入は正本のマージ後に既存のスキル配布手順を使い、導入済みファイルと正本を比較する。

実運用では、照合漏れ、誤検出、再読した資料、重複承認、状態確認の再実行を記録する。
時間・トークン量が取得できない場合は未測定とし、自動化だけで削減できたと断定しない。
例外が出た場合は検査を無効化して進めず、該当段階の手動手順へ戻して根拠と未確認事項を報告する。
初版の実装へ進む前に、plan/resultのschema、CI policyの正本、対象外差分の停止条件をPR単位で再確認する。
