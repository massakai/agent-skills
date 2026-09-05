---
name: mermaid-validate-and-render
description: "Mermaid の作成・修正時に、Markdown内の図や.mmdを一括でparse・描画し、変更図の再検証と目視確認を行う。"
---

# Mermaid Validate And Render

Mermaid は構文検証・実描画・目視確認を経て完成扱いにする。Markdownを編集している場合は、そのコードブロックを正本にし、検証用.mmdを別途編集しない。

## 実行

`scripts/` はこのスキルの配置先から解決する。依存の準備、全オプション、結果形式、旧コマンドは [install-and-usage.md](references/install-and-usage.md) を参照。

1. 図を作成・修正する。必要に応じて [authoring-rules.md](references/authoring-rules.md) と [diagram-patterns.md](references/diagram-patterns.md) を読む。
2. 関連する文書を**専用コマンド1呼出し**にまとめる。各図に対して同一ブラウザ・同一Mermaid依存でparse→renderする。

   ```sh
   node scripts/batch_mermaid.mjs --format png,svg document-a.md document-b.md diagram.mmd
   ```

   PNGは白背景が標準。透明背景は `--background transparent`、レイアウト幅は `--width 1600`。明示的な保存先は `--out-dir <出力ディレクトリ>` で指定する。省略時はOSの一時ディレクトリに保持され、JSONに保存先が出る。毎回の一時スクリプト作成や図ごとのコマンド分割は不要。
3. `report.json` の `id`（絶対ファイル名#Mermaidブロック番号）、見出し、行番号、各工程の結果を確認する。
   - `syntax`: 対象図の構文を直す。
   - `render`: 描画処理のエラーを調べて対象図・設定を直す。例は [common-errors.md](references/common-errors.md)。
   - `environment`: ブラウザ起動・権限・依存・出力先などを直す。図の構文を推測で変更しない。
   - `input`: 入力形式、抽出範囲、図IDなどを直す。
4. ソース変更後はparseから再開する。次の呼出しはハッシュが一致する成功結果を再利用し、変更図や未完了工程を処理する。

   ```sh
   node scripts/batch_mermaid.mjs --format png,svg --resume <前回のreport.json> document-a.md document-b.md diagram.mmd
   ```

   対象を限定するなら `--only '<report内のid>'`（繰返し可）を追加する。前回と同じ入力一覧・描画オプションを渡す。選択外の未検証図は `not_run` のままで、全体成功にはならない。
5. PNGを画像表示ツールで開き、日本語の欠け、ラベルの重なり、切れ、線と背景のコントラストを確認する。問題があれば正本を直し、再検証する。自動結果の `success` は目視確認済みを意味しない。
6. 各工程の成功・再利用・失敗・未実行、目視確認、生成物パス、残る制約を報告する。一時出力は確認完了まで保持し、不要になったこの実行専用ディレクトリだけを削除する。

## 権限エラー

ブラウザ起動はparseにも必要。保存先を変えるだけでは起動権限の問題は解決しない。起動失敗時は1回の試行で止まり、残る図を成功にしない。

実行環境の承認手順に従い、入力一覧・出力先・専用 `batch_mermaid.mjs` の実行範囲を示して同じコマンドを再実行する。ソースが不変で、成功済みparseの記録があれば `--resume` で再利用する。起動前に失敗してparse未実行なら、再実行でparseも必要。

承認回避、広いnode/bashの許可、サンドボックス無効化、別ツールへの切替えによる権限回避を解決策にしない。1呼出し・1ブラウザ起動にまとめても、承認回数は環境のポリシーに依存し、1回とは保証しない。
