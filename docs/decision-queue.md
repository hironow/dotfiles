# Decision Queue

このファイルはアシスタントが判断保留・要人間レビューの事項を記録するキューです。

## フォーマット
- `- [ ]` : 未対応
- `- [x]` : 対応済み

各エントリ: `- [ ] **<repo>**: <判断事項> — 背景 / 選択肢 / 推奨`

---

## 2026-06-10

- [ ] **kkk**: Takumi Guard 未導入 — `bun install` のみ使用（bun は Takumi Guard npm 公式未サポート）。npm guard 挿入スキップ。bun 公式対応を待って再検討。
- [ ] **writing**: Takumi Guard 未導入 — `bun install` のみ使用（bun は Takumi Guard npm 公式未サポート）。npm guard 挿入スキップ。
- [ ] **notifoo**: Takumi Guard 未導入 — `bun install` および `bunx playwright` のみ使用（bun は Takumi Guard npm 公式未サポート）。npm guard 挿入スキップ。
- [ ] **async/typescript-unit**: Takumi Guard 未導入（部分）— ci.yaml の `typescript-unit` ジョブは `bun install` 使用。bun 未サポートにつき挿入スキップ。他ジョブ（python-unit/integration/go-unit/e2e）は guard 導入済み。
- [ ] **homebrew-tap**: Takumi Guard 未導入 — CI は `brew audit` のみで Go/Python/npm のパッケージインストールステップなし。Guard 挿入対象なし。
- [ ] **bitcoin-watcher**: Takumi Guard 未導入 — CI は Cloud Build 起動のみで依存インストールステップなし。Guard 挿入対象なし。
- [ ] **nn-makers**: Takumi Guard 未導入 — CI は Cloud Build 起動のみで依存インストールステップなし。Guard 挿入対象なし。
- [ ] **just-ag/bun 系 workflows**: mcps-ci.yaml/test-ts、agent-hub-ci.yaml/frontend、browser-stream-ci.yaml/ci、tldraw-sync-ci.yaml/ci、moodboard-ci.yaml/ci、experiments-ci.yaml/bun-esm-bug-repro は全て `bun install` 使用。bun 未サポートにつき挿入スキップ。
