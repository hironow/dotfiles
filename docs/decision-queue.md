# Decision Queue

このファイルは tooling 巡回エージェントが人間の判断を求める事項を積むキュー。
エージェントは `## YYYY-MM-DD` セクションに `- [ ] **<repo>**: <判断事項>` の形式で追記する。
処理済みは `- [x]` に変更する。

## 2026-06-10

### セッション制約（重要）

本セッションは GitHub MCP のアクセス範囲が `hironow/dotfiles` のみに制限されていたため、
以下の作業が未実施:
- 他リポジトリの dependabot PR のマージ（access denied）
- 他リポジトリの tooling ゲート点検（access denied）

次回の巡回セッションでは **全 hironow リポジトリを scope に追加** して再実行が必要。

---

### A. Major version bumps（自動マージ禁止 — 採否を判断してください）

- [ ] **rain#10**: `ci: bump actions/checkout from 2 to 6` — GitHub Actions major (v2→v6)。actions/checkout v4 が LTS。v6 の breaking changes を確認の上採否決定。推奨: v4 固定を検討
- [ ] **my-tax#25**: `ci: bump extractions/setup-just from 3 to 4` — just セットアップ action の major bump。v4 リリースノートを確認して採否決定
- [ ] **env-template-PoC#9**: `ci: bump actions/checkout from 2 to 6` — 同上 (rain#10 と同内容)
- [ ] **fai-run#3**: `Bump svelte from 3.55.0 to 4.2.19` — Svelte 3→4 は breaking changes 多数。推奨: Svelte 4 移行ガイドを参照して手動移行
- [ ] **rain-san#3**: `Bump vite from 4.5.0 to 5.0.12` — Vite 4→5 は breaking changes あり。推奨: Vite 5 移行ガイドを参照
- [ ] **rain#8**: `bump node from 19-alpine to 26-alpine` (docker group) — Node.js major 19→26。Node 19 は EOL 済み。推奨: LTS の Node 22 または 24 に更新を検討
- [ ] **bito-option#22**: `bump node from 22-slim to 26-slim` (docker group) — Node.js 22→26。Node 22 はアクティブ LTS で安定。Node 26 は新しい。推奨: Node 24 LTS に固定するか v26 採用か決定

---

### B. Group PRs（差分未確認 — major bump 含まれないか要確認）

セッション制約により各 PR の差分を確認できなかった。内部に major bump が含まれないか確認後、問題なければマージ推奨。

- [ ] **mobile-chat-like#24**: `ci: bump the github-actions group with 2 updates`
- [ ] **my-tax#26**: `chore(deps): bump the npm group in /apps/viewer-ui with 15 updates`
- [ ] **rain#11**: `chore(deps): bump the pip group in /server with 8 updates`
- [ ] **fast#10**: `chore(deps): bump the pip group with 20 updates`
- [ ] **yui#28**: `chore(deps): bump the npm group in /frontend with 10 updates`
- [ ] **next#8**: `chore(deps): bump the npm group with 17 updates`
- [ ] **rain-san#8**: `chore(deps): bump the npm group across 2 directories with 24 updates`
- [ ] **rain#9**: `chore(deps): bump the npm group in /client with 23 updates`
- [ ] **hironow-test-fdc#4**: `chore(deps): bump the npm group in /email-app with 15 updates`
- [ ] **fai-run#6**: `chore(deps): bump the npm group with 19 updates`
- [ ] **myanimelist_sdk#9**: `chore(deps): bump the uv group with 7 updates`
- [ ] **myanimelist_sdk#8**: `ci: bump the github-actions group with 2 updates`
- [ ] **fast#9**: `chore(deps): bump python from 3.10-slim to 3.14.5-slim` (docker group) — Python 3.10→3.14 はマイナー。マージ推奨
- [ ] **check-copy-trade#13**: `chore(deps): bump the pip group with 10 updates`
- [ ] **fetch-rag#5**: `chore(deps): bump the uv group with 14 updates`
- [ ] **afpbb#8**: `chore(deps): bump the pip group with 34 updates`
- [ ] **bito-option#23**: `chore(deps): bump the npm group with 15 updates`
- [ ] **check-copy-trade#12**: `chore(deps): bump python from 3.10-slim to 3.14.5-slim` (docker group) — 同上 Python minor
- [ ] **async#32**: `chore(deps): bump the npm group in /impl/ts with 4 updates`
- [ ] **async#31**: `chore(deps): bump the gomod group in /impl/go with 5 updates`
- [ ] **check-copy-trade#11**: `ci: bump the github-actions group with 2 updates`
- [ ] **async#30**: `chore(deps): bump the docker group across 2 directories with 3 updates`
- [ ] **bbb#16**: `chore(deps): bump the gomod group across 2 directories with 4 updates`
- [ ] **bito-option#21**: `ci: bump the github-actions group with 2 updates`
- [ ] **bbb#15**: `ci: bump the github-actions group with 3 updates`
- [ ] **next#5**: `Bump postcss and next` — next (Next.js) の major bump の可能性あり。版数確認が必要
- [ ] **ath-atl-checker#3**: `Bump ws and puppeteer` — 複数パッケージ混在。各版数を確認
- [ ] **team-lgtm#30**: `Bump minimist and mkdirp` — 複数パッケージ混在
- [ ] **team-lgtm#27**: `Bump json5, css-loader, webpack, style-loader, ts-loader and webpack-cli` — webpack の major bump 含む可能性

---

### C. Minor/patch PRs（自動マージ推奨 — access denied のため未実施）

次回セッションで適切な scope で再実行、または手動でマージ推奨。
いずれも CI が CLEAN であることを確認してからマージすること。

| リポジトリ | PR | タイトル | 種別 |
|---|---|---|---|
| crediflow | #8 | bump cloud.google.com/go/texttospeech 1.6.0→1.21.0 | minor |
| gentypes | #5 | bump golang.org/x/tools 0.28.0→0.45.0 | minor |
| async | #27 | bump pytest-asyncio 1.3.0→1.4.0 (/impl/tests) | minor |
| async | #23 | bump pytest-asyncio 1.3.0→1.4.0 (/impl/py) | minor |
| gpu-using-with-poetry | #1 | Bump torch 2.0.1→2.2.0 | minor |
| ath-atl-checker | #2 | Bump @grpc/grpc-js 1.9.7→1.9.15 | patch |
| hironow-test-fdc | #1 | Bump @grpc/grpc-js 1.9.14→1.9.15 | patch |
| ath-atl-checker | #1 | Bump express 4.18.2→4.19.2 | minor |
| rain-san | #5 | Bump ip 2.0.0→2.0.1 | patch |
| rain-san | #4 | Bump vite 4.5.0→4.5.2 | patch |
| hironow-dev | #5 | Bump @babel/traverse 7.20.8→7.23.2 | minor |
| check-copy-trade | #8 | Bump urllib3 2.0.4→2.0.7 | patch |
| fast | #6 | Bump urllib3 2.0.3→2.0.7 | patch |
| afpbb | #5 | Bump urllib3 2.0.2→2.0.7 | patch |
| hironow-dev | #4 | Bump postcss 8.4.20→8.4.31 | patch |
| fast | #4 | Bump cryptography 41.0.1→41.0.4 | patch |
| afpbb | #3 | Bump cryptography 41.0.1→41.0.4 | patch |
| next | #4 | Bump protobufjs 6.11.3→6.11.4 | patch |
| hironow-dev | #3 | Bump json5 1.0.1→1.0.2 | patch |
| fast | #2 | Bump certifi 2023.5.7→2023.7.22 | minor |
| afpbb | #1 | Bump certifi 2023.5.7→2023.7.22 | minor |
| hironow-dev | #2 | Bump semver 5.7.1→5.7.2 | patch |
| hironow-dev | #1 | Bump word-wrap 1.2.3→1.2.5 | patch |
| fast | #1 | Bump aiohttp 3.8.4→3.8.5 | patch |
| rain | #3 | Bump word-wrap 1.2.3→1.2.4 | patch |
| next | #2 | Bump word-wrap 1.2.3→1.2.4 | patch |
| next | #1 | Bump semver 6.3.0→6.3.1 | patch |
| rain | #2 | Bump semver 6.3.0→6.3.1 | patch |
| crediflow | #5 | Bump vite 4.1.3→4.1.5 | patch |
| crediflow | #4 | Bump @sveltejs/kit 1.7.2→1.15.2 | minor (v1 内) |
| team-lgtm | #33 | Bump golang.org/x/sys → 0.1.0 | minor |
| team-lgtm | #32 | Bump golang.org/x/net → 0.7.0 | minor |
| team-lgtm | #31 | Bump golang.org/x/text 0.3.2→0.3.8 | patch |
| team-lgtm | #29 | Bump ua-parser-js 0.7.32→0.7.33 | patch |
| team-lgtm | #28 | Bump json5 1.0.1→1.0.2 | patch |
| team-lgtm | #26 | Bump decode-uri-component 0.2.0→0.2.2 | patch |
| team-lgtm | #24 | Bump moment 2.24.0→2.29.4 | minor |
| env-template-PoC | #6 | Bump shell-quote 1.7.2→1.7.3 | patch |
| team-lgtm | #21 | Bump url-parse 1.4.7→1.5.10 | minor |
| env-template-PoC | #5 | Bump path-parse 1.0.6→1.0.7 | patch |
| team-lgtm | #14 | Bump dns-packet 1.3.1→1.3.4 | patch |
| env-template-PoC | #4 | Bump hosted-git-info 2.8.8→2.8.9 | patch |
| team-lgtm | #13 | Bump lodash 4.17.11→4.17.21 | patch |
| team-lgtm | #10 | Bump ssri 6.0.1→6.0.2 | patch |
| team-lgtm | #7 | Bump ini 1.3.5→1.3.7 | patch |
| team-lgtm | #3 | Bump websocket-extensions 0.1.3→0.1.4 | patch |

---

### D. Tooling ゲート点検（access denied で未実施）

- [ ] **全リポジトリ（100件）**: セッション scope が `hironow/dotfiles` のみのため tooling ゲート点検が実施不可。次回セッションで全 hironow リポを scope に追加して再実行。
  点検対象: `.pre-commit-config.yaml` / `.markdownlint.json` / `.markdownlint-cli2.yaml` / `justfile` (fmt/lint/check/install-hooks レシピ)

---

### E. 巡回エージェント設定の改善依頼

- [ ] **session scope の拡張**: 次回巡回セッション起動時は `hironow/*` 全リポジトリを GitHub MCP の allowed repositories に含めること。現状 `hironow/dotfiles` のみでは他リポへのマージ・ファイル読み取りが不可で、巡回エージェントとして機能しない。

---

### F. Takumi Guard 導入 — Bun 非対応ジョブ

Takumi Guard の npm action は Bun パッケージマネージャーに対応していない。以下のジョブで `bun install` が使われており、Guard を挿入できなかった。Bun 対応の supply chain 防御ツールの採用、または当該ジョブの npm/pnpm 移行を検討してください。

- [ ] **async**: `ci.yaml` `typescript-unit` ジョブ — `setup-bun + bun install --frozen-lockfile`
- [ ] **kkk**: `ci.yaml` `unit` / `e2e` / `scenarios` ジョブ — `mise exec -- bun install --frozen-lockfile`（`unit` ジョブの pip install には PyPI Guard 挿入済）
- [ ] **just-ag**: `mcps-ci.yaml` `test-ts` ジョブ — `bun install --frozen-lockfile`
- [ ] **just-ag**: `agent-hub-ci.yaml` `frontend` / `frontend-integration` ジョブ — `bun install`
- [ ] **just-ag**: `browser-stream-ci.yaml` — `bun install` のみ（Guard 未挿入）
- [ ] **just-ag**: `moodboard-ci.yaml` — `bun install` のみ（Guard 未挿入）
- [ ] **just-ag**: `tldraw-sync-ci.yaml` — `bun install` のみ（Guard 未挿入）
- [ ] **just-ag**: `experiments-ci.yaml` — `bun install` のみ（Guard 未挿入）
- [ ] **notifoo**: `ci.yaml` — `setup-bun + bun install` のみ（Guard 未挿入）
- [ ] **writing**: `ci.yml` — `bun install --frozen-lockfile` のみ（Guard 未挿入）

---

### G. CI 未整備リポジトリ（Takumi Guard 対象外）

以下のリポジトリは `.github/workflows/` が存在しないか CI が未設定のため Takumi Guard を挿入できなかった。CI 整備および Guard 導入を検討してください。

- [ ] **gentypes** — CI なし
- [ ] **my-rpc** — CI なし
- [ ] **research** — CI なし
- [ ] **weaveback** — CI なし
- [ ] **chrome-extensions-n-img-to-zip** — CI なし
- [ ] **cryptoquant** — CI なし
- [ ] **animation** — CI なし
- [ ] **audio** — CI なし
- [ ] **auto-amv** — CI なし
- [ ] **cloud** — CI なし
- [ ] **cyber** — CI なし
- [ ] **deep-research** — CI なし
- [ ] **fetch-rag** — CI なし
- [ ] **garnish** — CI なし
- [ ] **knowledge-work-plugins** — CI なし
- [ ] **search-ja-persona** — CI なし
- [ ] **skills** — CI なし
- [ ] **x-download** — CI なし
- [ ] **adk-stream-protocol** — CI なし
- [ ] **code** — CI なし
- [ ] **k3** — CI なし
- [ ] **moltbot-sandbox** — CI なし
- [ ] **nostra** — CI なし
- [ ] **semgrep-guardrails** — CI なし
- [ ] **vibe-coding-platform** — CI なし
- [ ] **vsano** — CI なし
