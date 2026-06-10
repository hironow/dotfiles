# 0026. Antigravity CLI: instruction 層のみ共有、skills/settings/mcp は agy 委譲

**Date:** 2026-06-10
**Status:** Accepted

## Context

Google は **Gemini CLI を 2026-06-18 に sunset** し（AI Pro/Ultra/free の Gemini
CLI および Gemini Code Assist IDE 拡張がリクエスト停止）、後継 **Antigravity CLI
(`agy`)** へ移行する（公式 developers blog / antigravity.google、2026-05 発表）。
本機では `agy` 1.0.6 が mise 経由で install 済み、`~/.gemini/antigravity-cli/` が
active な config dir。

dotfiles は `just sync-agents` (`scripts/sync_agents.py`) で hub-and-spoke の agent
指示を配布する。gemini ターゲットは base を **`~/.gemini/GEMINI.md`** へ書く。Gemini
CLI 退役にあたり「gemini への配布を Antigravity 用に移す/拡張する必要があるか」を
調査した結果、以下が判明した:

1. **instruction 層は既に共有**。Antigravity CLI は global rules に
   **`~/.gemini/GEMINI.md` を引き続き使う**（全 workspace で自動 load/enforce、
   `google-gemini/gemini-cli#16058` で両者が同ファイルへ書く挙動も確認）。dotfiles の
   base sync 先は移動不要で、既存 gemini ターゲットがそのまま Antigravity を兼ねる。
2. **skills は `agy plugin` 管理**。Antigravity の skills は
   `~/.gemini/antigravity-cli/plugins/<name>/skills/` に plugin 単位で入り、
   `agy plugin install/import` で投入される。dotfiles の `bunx skills` CLI 委譲と同型。
3. **settings/mcp は user-runtime + `agy import` 管理**。
   `~/.gemini/antigravity-cli/settings.json` は model/permissions/oauth 等の個人状態、
   `mcp/` は `agy` が gemini-cli から import した per-server dir。dotfiles が raw sync
   すると、これら agy/個人所有の状態を clobber する。

## Decision

Antigravity CLI 移行に対し、dotfiles は **instruction 層のみを共有し、skills/
settings/mcp は `agy` の自己管理に委ねる**。

1. **base (`~/.gemini/GEMINI.md`) の sync は無変更**。Gemini CLI と Antigravity CLI
   が同一ファイルを読むため、既存 gemini ターゲットがそのまま両者を兼ねる。`agy` 専用
   ターゲットや配布先の移動は追加しない。
2. **skills を Antigravity へ raw sync しない**。skills の投入は `agy plugin` に委ねる
   （dotfiles が `bunx skills add` を優先するのと同じ理由 = CLI 管理層を迂回しない）。
3. **settings/mcp を sync しない**。これらは個人 runtime かつ `agy import` 管理であり、
   dotfiles が書くと上書き事故になる。
4. 上記の現状と境界を `CLAUDE.md`（repo dev rules の「二層構造」節）と
   `scripts/sync_agents.py` の gemini ターゲット行コメントに記録する。

この決定はコード/配布挙動を変えない（`just sync-agents-preview` の計画は不変）。
変更は docs のみ。

## Consequences

### Positive

- Gemini CLI 退役後も agent 指示が途切れない（`~/.gemini/GEMINI.md` 共有のため
  Antigravity が同じ base を読む）。配布コードの変更ゼロでリスク最小。
- Antigravity の個人 runtime（model 選択 / permissions / oauth-token）と `agy import`
  済み mcp/skills を dotfiles が clobber しない。CLI 委譲方針が gemini/claude/codex と
  一貫する（skills は常に CLI 管理）。

### Negative

- dotfiles 管理の skills は Antigravity から自動では見えない。Antigravity で使いたい
  skill は `agy plugin` で別途投入する手作業が要る（`bunx skills` と同じ運用負荷）。
- 既存の `~/.gemini/skills/` additive 配布は Antigravity が plugins/ から読むため
  vestigial になる。additive ゆえ無害で残置するが、将来 Gemini CLI 完全廃止時に
  撤去するか否かは別途判断（本 ADR では撤去しない）。

### Neutral

- 将来 Antigravity が top-level `~/.gemini/antigravity-cli/skills/` の global skills を
  正式サポートし、かつ CLI 非経由の配布が妥当になった場合は、本決定を上書きする後続
  ADR で `secondary_skills_dest` 等の sync 拡張を再検討する余地を残す。
