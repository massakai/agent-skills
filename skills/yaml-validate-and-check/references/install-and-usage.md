# Install and usage

このスキルのローカル検証は Ruby 標準添付の `psych` を使う。

## Recommended Ruby version

- 推奨: `Ruby 3.1+`
- 理由: このスキルは `psych` を前提にしており、`Ruby 3.1.0` で動作確認済み
- `Ruby 2.7+` でも動く可能性はあるが未検証

## Validate

```sh
ruby scripts/validate_yaml.rb path/to/file.yml
```

成功時は document 数と root node 種別を表示する。失敗時は構文エラー、または重複キーを表示して non-zero で終了する。

## What this validator checks

- YAML として parse できること
- 同一 mapping 内の重複キーがないこと

## What this validator does not check

- GitHub Actions や Kubernetes など利用先固有の schema
- semantic な整合性
- コメント保持を伴う format 変更

利用先固有の validator がある場合は、この検証のあとに必ず追加で実行する。
