# Common YAML errors

## Mapping values are not allowed here

ありがちな原因:

- インデントずれ
- `:` を含む文字列の未 quote

まず確認すること:

- 問題行の前後でインデント幅がそろっているか
- URL、時刻、説明文などに `:` が含まれていないか

## Did not find expected key

ありがちな原因:

- 配列要素の `-` の位置がずれている
- 複数行文字列のインデントが足りない
- Markdown のつもりで値をバッククォート囲みした

対処:

- YAML ではバッククォートは文字列記法ではないので、通常は `'` か `"` に置き換える
- コードっぽい値を入れたいだけなら quote した plain string にする

## Duplicate key

ありがちな原因:

- 同じ section に同名 key を後から足した
- merge 後に古い key が残った

対処:

- どちらを残すべきか判断して 1 つにする
- 意図的な上書きに見えても、YAML 利用側の挙動が不安定になるので避ける

## Boolean / number coercion

ありがちな原因:

- `on`, `off`, `yes`, `no`, `00123` を文字列のつもりで書いた

対処:

- 文字列として扱いたい値は quote する

## Shape mismatch after parse

症状:

- YAML としては valid だが、利用先でエラーになる

対処:

- top-level key 名を確認する
- 配列の想定箇所に mapping を置いていないか確認する
- 利用先の schema や validator があるなら必ず実行する
