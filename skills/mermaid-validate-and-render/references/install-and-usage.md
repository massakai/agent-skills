# Install And Usage

## 導入と更新

公開された管理元から対象スキルを導入する。未公開worktreeの変更はこの操作には含まれない。

```sh
npx skills add massakai/agent-skills --skill mermaid-validate-and-render
```

必要なら `-g` や `--agent <agent-name>` を追加する。インストール先のスキルディレクトリで `npm ci` を実行し、lockfileの依存を用意する。Node.jsは依存パッケージのenginesを満たす版を使用する（現行lockfileはNode.js 22.12以上）。Chromiumと日本語フォントも必要。Puppeteerのインストールスクリプトがローカルのパッケージ管理ポリシーで保留された場合は、そのポリシーに従って依存のセットアップを完了する。

```sh
node scripts/batch_mermaid.mjs --format png,svg examples/sample-document.md examples/sample-flowchart.mmd
```

生成PNGを開いて確認する。インストール済みスキルの更新や承認設定変更は、スキル管理元の編集とは別操作。更新後は依存を揃え、必要なら利用エージェントのセッションを再起動する。

## 一括コマンド

```sh
node scripts/batch_mermaid.mjs [options] INPUT...
```

| オプション | 意味 |
| --- | --- |
| `--out-dir DIR` | 出力先。省略時は `os.tmpdir()` 内に専用ディレクトリを作る |
| `--format png,svg` | `png`（標準）、`svg`、または両方 |
| `--background COLOR` | `white`（標準）、`transparent`、CSS色 |
| `--width N` | ブラウザのレイアウト幅、標準1200px。画像の最終幅を強制する値ではない |
| `--config FILE` | parse・render共通のMermaid JSON設定 |
| `--puppeteer-config FILE` | Puppeteer起動設定。省略時は `PUPPETEER_CONFIG_FILE`、さらに省略時はheadless shell |
| `--resume REPORT` | 前回のJSONから一致する成功工程を再利用 |
| `--only ID` | `report.json` の絶対ファイル名#ブロック番号。繰返し可 |
| `--parse-only` | 構文確認のみ。実描画完了を意味しない |

Markdownはトップレベルのbacktick/tildeフェンスを扱う。情報文字列の先頭が `mermaid` のブロックを文書内の順番で番号付けする。他言語フェンス内のサンプルは抽出しない。ATX/Setext見出しとソース開始行を記録する。リスト・引用内などのコンテナ入れ子は対応範囲外で、検出した入れ子Mermaidは入力エラーにする。Markdownの完全な構文解析器ではないため、複雑なコンテナ構文の文書は事前に対応範囲を確認する。閉じていないMermaidフェンスも入力エラー。`.mmd` はファイル全体が1図。

ブロック追加・並替えでIDが変わる場合は現在の一覧で再実行する。同じファイルを複数回渡しても重複処理しない。入力なし・図なし・不明IDは成功にしない。

## 結果と再実行

標準出力と出力ディレクトリの `report.json` に、入力ハッシュ（抽出後のソース）、ファイル・見出し・番号・行、依存/Node/起動したブラウザの版、設定、実装ハッシュ、各工程の結果、生成物パス/ハッシュ、ブラウザ起動試行数/成功数を記録する。起動設定は秘密値を露出しないようハッシュだけ記録する。

- 終了コード0: このモードの全対象成功。`parse-only` のrenderは未実行。
- 終了コード1: 環境・引数エラー。
- 終了コード2: 構文・描画・抽出エラー、または未完了の図あり。
- 工程の `success` / `failed` / `not_run` を区別する。`reused: true` は今回実行した成功ではなく、照合済みの前回記録。

再利用はソース、実装、Node/Mermaid/Puppeteer版、Mermaid設定の一致が必要。描画には背景・幅・形式・起動設定の一致と、既存生成物の内容ハッシュ一致も必要。ソースが変わればparseから実行する。parse成功後の出力障害なら、ソース不変の再実行でparseを再利用してrenderを再試行できる。

`--resume` でも全入力を読み直すが、変更なしの成功図はブラウザを起動しない。選択外の未完了は隠さない。再利用された生成物は元の場所を参照し、新出力先へコピーしない。前の出力ディレクトリを消すと再描画が必要になる。フォント、OS、差替えられたブラウザ実体まではキャッシュキーで保証しない。それらを変えた場合や独立した再確認では `--resume` を外す。別環境の結果や信頼できないJSONを成功根拠として渡さない。

バッチ出力は目視確認と再実行のため保持する。検証用ソースコピーは作らない。明示した専用出力先を優先し、同じ出力先への並行実行は避ける。古い生成物が残っていても、現行レポートの成功工程と対応付けられなければ成功根拠にしない。ブラウザと各ページは処理後に閉じる。確認後は実行専用出力ディレクトリを削除できる。

## 旧単一図コマンド

呼出し形を維持し、同じ実装・ローカル依存へ統一した。

```sh
node scripts/validate_mermaid.mjs input.mmd [puppeteer-config.json]
bash scripts/render_mermaid.sh input.mmd output.svg [mermaid-config.json] [puppeteer-config.json]
```

`validate` はparseのみ（結果JSONの保存先はOS一時ディレクトリ）。`render` はparse→renderを実行し、指定したSVG/PNGへ出力後、内部一時ディレクトリを後片付けする。出力先の親ディレクトリは先に用意する。

背景標準は旧transparentからwhiteへ変更。透明が必要なら一括コマンドの正式オプションを使う。グローバル `mmdc` と `MMDC` overrideは参照しない。旧renderのSVG/PNG入力形・JSON設定引数を保つが、mmdc固有のPDF出力は対応しない。parseとrenderを旧コマンドで別々に呼ぶとブラウザも2回起動するため、通常は一括コマンドを使う。

## 開発時の検証

`npm test` は抽出・引数、`npm run test:browser` は実ブラウザで構文混在・修正再実行・生成物破損・透明背景・環境障害・旧コマンドを検証する。後者は目視確認用の一時成果物を保持し、その場所を表示する。ブラウザ実行に承認が必要なら通常の承認手順を使う。
