# YAML authoring rules

YAML は見た目の自由度が高いぶん、曖昧さで壊れやすい。迷ったら短く明示的な書き方を優先する。

## 基本ルール

- インデントはスペースのみを使う
- ネストの深さが変わる場所では、同じ段の key をそろえる
- 1 行で済む scalar は無理に複数行にしない
- 真偽値や数値に見える値は、文字列として扱いたいなら quote する
- `:` `#` `{}` `[]` を含む文字列は quote を優先する
- Markdown の癖で値をバッククォート囲みしない。YAML ではコード表現にならず、構文エラーや意図しない値になりやすい
- 空配列は `[]`、空 mapping は `{}` を使うと意図が明確になる

悪い例:

```yaml
message: `hello`
```

安全側の例:

```yaml
message: "hello"
```

## 複数行文字列

- 改行を保ちたいなら `|`
- 折り返して 1 行として扱いたいなら `>`
- 行末空白やインデント混在を避ける

## 配列と mapping

- 配列要素の直下に mapping を置くときは、`-` のあとを詰め込みすぎない
- deeply nested な inline 記法より block style を優先する

悪い例:

```yaml
items: [{name: app, enabled: true}, {name: worker, enabled: false}]
```

安全側の例:

```yaml
items:
  - name: app
    enabled: true
  - name: worker
    enabled: false
```

## anchor / alias

- anchor と alias は本当に繰り返しが多い場合だけ使う
- 利用先が anchor を正しく扱うか不明な場合は展開した形を優先する

## document separator

- 複数 document が必要な場合だけ `---` を使う
- `...` は明確な理由がない限り省略してよい
