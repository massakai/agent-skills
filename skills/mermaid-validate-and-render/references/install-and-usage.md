# Install And Usage

## インストール

### GitHub から追加する

GitHub に公開したスキルリポジトリから `npx skills` で追加します。

このリポジトリのように複数スキルを含む場合は、`--skill mermaid-validate-and-render` を付けて対象スキルを絞ります。

例:

```sh
npx skills add massakai/agent-skills --skill mermaid-validate-and-render
```

グローバルに入れたい場合:

```sh
npx skills add massakai/agent-skills --skill mermaid-validate-and-render -g
```

インストール前に対象スキル一覧だけ確認したい場合:

```sh
npx skills add massakai/agent-skills --list
```

エージェント指定が必要な環境では、利用先のエージェントを追加指定します。

```sh
npx skills add massakai/agent-skills --skill mermaid-validate-and-render --agent <agent-name>
```

### 依存の準備

スクリプトがローカルの `node_modules` を使えるように、スキルディレクトリで実行します。

```sh
cd <skills により展開された mermaid-validate-and-render ディレクトリ>
npm install
```

これで次が入ります。

- `mermaid` for `scripts/validate_mermaid.mjs`
- `@mermaid-js/mermaid-cli` for `scripts/render_mermaid.sh`

必要な前提:

- Node.js 20 以上
- npm

### `npm warn allow-scripts` が出る場合

npm の設定によっては、`npm install` 時に `puppeteer` の install script が未承認として警告されることがあります。

例:

```text
npm warn allow-scripts 1 package has install scripts not yet covered by allowScripts:
npm warn allow-scripts   puppeteer@... (postinstall: node install.mjs)
```

この場合は `puppeteer` を承認してください。

```sh
npm approve-scripts puppeteer
```

保留中の script をまとめて確認したい場合:

```sh
npm approve-scripts --allow-scripts-pending
```

承認後、必要なら `npm install` を再実行します。`validate_mermaid.mjs` と `render_mermaid.sh` が成功すれば準備完了です。

### インストール確認

次を実行します。

```sh
cd <skills により展開された mermaid-validate-and-render ディレクトリ>
node scripts/validate_mermaid.mjs examples/sample-flowchart.mmd
scripts/render_mermaid.sh examples/sample-flowchart.mmd /tmp/sample-flowchart.svg
```

期待結果:

- parser 検証が成功終了する
- render が成功終了し、SVG が出力される

Codex からスキルが認識されることを確認するには、`$mermaid-validate-and-render` を明示したプロンプトを開始します。起動時にスキル一覧をキャッシュする環境では、`npx skills add` 実行後にセッション再起動が必要な場合があります。

### サンドボックス環境や CI での render

Chromium 起動に `--no-sandbox` が必要な環境では、Puppeteer 設定ファイルを作成してスクリプトへ渡します。

```json
{
  "args": ["--no-sandbox"]
}
```

実行例:

```sh
node scripts/validate_mermaid.mjs \
  examples/sample-flowchart.mmd \
  ./puppeteer-config.json

scripts/render_mermaid.sh \
  examples/sample-flowchart.mmd \
  /tmp/sample-flowchart.svg \
  "" \
  ./puppeteer-config.json
```

## 使い方

### 想定プロンプト

- `$mermaid-validate-and-render を使って、会員登録フローの flowchart を作って`
- `$mermaid-validate-and-render を使って、この render に失敗する Mermaid を修正して`
- `$mermaid-validate-and-render を使って、この sequenceDiagram をコミット前に検証して`

### 新規作成時

1. 図の種類を決める
2. 最小の有効な Mermaid を作る
3. `parse` を検証する
4. `render` を検証する
5. 両方成功した Mermaid だけを返す

### 修正時

1. 失敗している Mermaid をファイルに保存する
2. まず `parse` を実行する
3. `parse` が失敗したら構文を直して再検証する
4. `parse` 成功後に `render` を実行する
5. `render` が失敗したら Mermaid を直し、必ず `parse` からやり直す

### エラー時の扱い

- `parse` 失敗: その時点で未完了。render を推測で続けない
- `render` 失敗: その時点で未完了。修正後は必ず `parse` へ戻る
- 失敗が続く: `diagram-patterns.md` の最小テンプレートへ戻し、段階的に再構築する
