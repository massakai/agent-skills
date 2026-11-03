# 取得と入力契約

Python 3.11以上の標準ライブラリだけで生成できる。
以下は架空の入力であり、実際のprivate repositoryの情報を共有スキルへ取り込まない。

```json
{
  "complete": true,
  "scope": "direct",
  "root_url": "https://github.com/example/demo/issues/1",
  "captured_at": "2026-01-01T10:00:00+09:00",
  "status_source": "Project example/2 / Status",
  "omitted_closed": [],
  "nodes": [
    {"url": "https://github.com/example/demo/issues/2", "title": "保存と読戻し", "kind": "child", "state": "OPEN", "status": "In Progress", "status_reason": "選択ProjectのStatusを取得", "blocked_by": []},
    {"url": "https://github.com/example/demo/issues/3", "title": "成果物の受入", "kind": "child", "state": "OPEN", "status": "Blocked", "status_reason": "選択ProjectのStatusを取得", "blocked_by": ["https://github.com/example/demo/issues/2"]}
  ]
}
```

## 収集

`gh api`のRESTとGraphQLで取得する。
RESTの一覧は`--paginate --slurp`、GraphQLの各connectionは`pageInfo.hasNextPage/endCursor`で最後まで取得する。
ネストしたconnectionも個別にページ送りし、最初の100件やProject itemの最初の1件だけを全件と扱わない。
大きいクエリはroot単位・Issue単位に分け、APIの上限に合わせる。

- 親と各Issue：`repos/{owner}/{repo}/issues/{number}`。
- 直接の子：`repos/{owner}/{repo}/issues/{number}/sub_issues`。
- 先行条件：`repos/{owner}/{repo}/issues/{number}/dependencies/blocked_by`。
- 状態：GraphQLのIssue `projectItems`→対象Projectのitem→`fieldValues`から、確定したfieldの値を取得する。

Projectはowner・番号またはnode IDで選び、表示名や並び順だけで別ProjectのStatusを採用しない。
直接の子はOPEN/CLOSEDを問わず全件含める。
`kind=child`は親のsub_issues APIで取得した所属にだけ付け、repositoryの一致や依存関係から推定しない。
この所属の正しさは入力作成者の照合責任であり、生成器はAPIの親子関係を再取得しない。
その全先行Issueを取得し、集合外でOPENなら`kind=boundary`として追加する。
境界ノードのblockedByも取得し、表示集合内の辺を残す。
新たな集合外OPEN先行が見つかったら境界集合を拡張し、有限な先行閉包の取得を完了する。
直接の子以外でCLOSEDの先行URLは`omitted_closed`へ入れる。
循環を探索の繰返しで隠さず、visited集合で停止して報告する。

全ページの取得証拠と照合を担当の作業記録へ残してから`complete=true`にする。
この値はAPI完全取得をスクリプトが証明した意味ではない。
`blocked_by`には省略する完了済み先行URLも含め、未知参照を残さない。
URLは同じGitHub host内のIssueを使い、repositoryをまたぐ同番号も区別する。
`status`には取得した文字列を保持する。
選択Projectへの未登録・field未設定は`Unknown`とその理由を記録し、Issue CLOSEDからDoneを推定しない。
認証・取得失敗時はJSONを完成品として生成しない。

## スクリプトの範囲

`render_graph.py`は入力の完全取得宣言、参照、重複、循環を検査し、Mermaidと管理ブロックを生成する。
各repositoryの業務受入条件、Projectの意味、元APIレスポンスの正しさを代替検証しない。
本文置換では管理マーカー外を保持する。
初回の配置と、更新先の公開範囲・承認の確認は担当が行う。
