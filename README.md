# agent-skills

GitHub で共有できる AI エージェント向けスキルを管理するリポジトリです。

このリポジトリは、再利用可能なスキル本体と、その作成・配布に必要な公開可能資料だけを扱います。Codex 全般の個人設定、認証情報、キャッシュ、ローカル環境固有の状態は管理しません。

## このリポジトリで扱うもの

- `skills/` 配下の共有スキル
- スキルの参照資料、サンプル、補助スクリプト
- スキル共有方針をまとめた [AGENTS.md](/Users/massakai/Documents/agent-skills/AGENTS.md)

## 扱わないもの

- 認証情報
- セッションデータ
- キャッシュ
- ローカルパスや端末依存設定
- 個人用の Codex 設定一式

## 構成

```text
.
├── README.md
├── AGENTS.md
└── skills/
    ├── README.md
    ├── _template/
    │   └── SKILL.md
    ├── mermaid-validate-and-render/
    │   ├── SKILL.md
    │   ├── agents/
    │   ├── examples/
    │   ├── references/
    │   └── scripts/
    └── repo-orientation/
        └── SKILL.md
```

## スキルの考え方

- 1 スキル 1 ディレクトリで管理する
- 入口ファイルは `SKILL.md` にする
- 複数プロジェクトで再利用できる形を優先する
- 秘密情報、非公開 URL、端末固有の前提を埋め込まない
- 大きな万能スキル 1 つより、小さく合成しやすいスキルを優先する

詳しい共有方針は [AGENTS.md](/Users/massakai/Documents/agent-skills/AGENTS.md)、`skills/` 配下の配置規約は [skills/README.md](/Users/massakai/Documents/agent-skills/skills/README.md) を参照してください。

## 使い方

このリポジトリのスキルは、GitHub から `npx skills` で導入する想定です。

```sh
npx skills add massakai/agent-skills --skill <skill-name>
```

例:

```sh
npx skills add massakai/agent-skills --skill mermaid-validate-and-render
```

スキルごとの追加依存や検証方法は、各スキルの `references/` や `SKILL.md` を参照してください。

## 新しいスキルの追加

1. `skills/_template/` を元に新しいディレクトリを作る
2. `SKILL.md` に目的、使う場面、手順、ガードレールを書く
3. 必要なら `references/`、`scripts/`、`examples/` を追加する
4. 例やサンプルは公開可能な内容だけにする
5. 共有方針に影響する変更がある場合は [AGENTS.md](/Users/massakai/Documents/agent-skills/AGENTS.md) も更新する
