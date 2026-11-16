# bunfig の minimumReleaseAge を秒で書く

**Date:** 2026-11-17
**Status:** 実装済み（Codex のレビュー 2 回で指摘なし）。merge の後に `just sync-agents all` と Dependabot の再実行で確かめる
**Scope:** dotfiles のみ。worktree `../dotfiles-bun-release-age`、branch `fix/bun-minimum-release-age-seconds`。
グローバルの spoke（`ROOT_AGENTS_docs_agents_web-ui.md`、`ROOT_AGENTS_docs_agents_dependency-policy.md`）も変えるので、merge の後に `just sync-agents` で配る。

## 所有者の依頼

所有者は「使う版は常に最新にしてほしい」と言い、書き方だけを秒に変える案（案 1）を選んだ（2026-11-17 02:15、「ok」）。
dependabot-core への issue は外部への投稿なので出さない。

## 何が起きているか（確認済みの事実）

- Dependabot の `bun` の job は、`bunfig.toml` の `minimumReleaseAge = "7d"` を読めずに失敗する（2026-11-16 14:36 UTC の job 1709041923。`Error: Expected number of seconds for minimumReleaseAge`）。
  `bun` は weekly の multi-ecosystem group に入っているので、この失敗でも週 1 の PR が出ない。
- Dependabot の bun は 1.4.2（dependabot-core `bun/Dockerfile` の `ARG BUN_VERSION=1.4.2`。最後の変更は 2026-10-06）。
- 期間の書き方（`90m`、`3d`、`2 weeks` など）は bun の PR #44968（2026-10-14 merge）で入った。`bun-v1.4.3` には入っておらず、`bun-v1.4.4`（2026-10-22、今の最新）に入っている（GitHub の compare で確認）。
- 手元で試した結果（`is-number@7.0.0` を入れるだけの一時の project）:

  | bun | `minimumReleaseAge = 604800` | `minimumReleaseAge = "7d"` |
  |---|---|---|
  | 1.4.4（手元、最新） | 成功 | 成功 |
  | 1.4.2（GitHub の公式リリースの zip。`SHASUMS256.txt` で照合） | 成功 | `Invalid Bunfig: failed to load bunfig`、exit 1 |

- 使う bun の版は変えない。手元と CI は最新の bun のまま。変えるのは `bunfig.toml` の書き方だけ。
- `"7d"` の書き方を決めているのは次の 3 か所。
    - `bunfig.toml`（ADR-0079 で入った。ADR-0079 の D2 は「7 日待つ」とだけ書き、書き方は決めていないので ADR は変えない）
    - グローバルの spoke `ROOT_AGENTS_docs_agents_web-ui.md` の「With a package:」の例
    - テスト `tests/unit/test_frontend_ci_conformance.py`（`== "7d"`）と `tests/unit/test_web_ui_guidance.py`（`'minimumReleaseAge = "7d"' in ...`）
- `.gpus` と shorts-factory には `bunfig.toml` の `minimumReleaseAge` も Dependabot の `bun` もない。

## 変更

1. **[Red]** テストを先に直す。
   - `test_frontend_ci_conformance.py`: `bunfig["install"]["minimumReleaseAge"] == 604800`。
   - `test_web_ui_guidance.py` の `test_the_wait_is_set_where_bun_installs`: 「With a package:」の段落に `minimumReleaseAge = 604800` がある。CLI の `--minimum-release-age 7d` の検査はそのまま（CLI は手元の最新の bun が読むので、期間の書き方でよい）。
   - `test_web_ui_guidance.py` の `test_the_dependency_policy_says_how_bun_waits`: dependency-policy の段落に `604800` と、Dependabot が秒しか読まないことの説明（`seconds`）がある。
2. **[Green]**
   - `bunfig.toml`: `minimumReleaseAge = 604800`。上のコメントに「7 日を秒で書く。Dependabot の bun（1.4.2）は `"7d"` を読めない」と書く。
   - `ROOT_AGENTS_docs_agents_web-ui.md`: 例を `[install] minimumReleaseAge = 604800`（7 日を秒で）にする。
   - `ROOT_AGENTS_docs_agents_dependency-policy.md`: bun の段落に「`bunfig.toml` では秒で書く（7 日は `604800`）。Dependabot の bun は `"7d"` のような期間を読めない」を足す。規則の本体はここに置き、web-ui の spoke は例だけにする（DRY）。

commit は 1 つ（`fix(bun): write minimumReleaseAge in seconds so Dependabot's bun can read it`）。構造の変更はない。

## 確認（完了の定義）

- `just ci` が完走して成功する（時間制限を付けずに回す）。`instruction-budget` の leg も含む。
- merge の前に、PR の branch の `bunfig.toml` を bun 1.4.2 と 1.4.4 の両方で読ませて、両方とも install が通ることを確かめる（上の表と同じ一時の project に、branch の `bunfig.toml` をそのまま置く）。
- PR の CI が green。所有者の常設の許可に従って squash merge する。
- merge の後:
    - 手元の main を pull し、`just sync-agents-preview all` で配る先と差分を確かめてから `just sync-agents all` で全エージェントに配る。配った各 home の `docs/agents/dependency-policy.md` と `docs/agents/web-ui.md` に `604800` が入ったことを確かめる。`~/.claude` だけに配ると、Codex や Gemini には古い `"7d"` の例が残る。
    - この変更の完了の条件は、Dependabot の再実行で `bun` の job から `Expected number of seconds for minimumReleaseAge` が消え、job が完走すること。週 1 の PR は、更新するものがあるときだけ開く（いまは oxlint 1.93.0 などがあるので開く見込み）。
- 失敗したとき: 原因を切り分ける。この変更が原因の失敗（bunfig を読めない、7 日の待ちが効かない）だと確かめたときだけ、squash commit を revert して `just sync-agents all` で配り直す。別のエコシステムの失敗や通信の失敗では revert しない（revert すると `"7d"` の読めない失敗が戻る）。再実行するか、別に直す。

## 範囲外

- dependabot-core への issue（外部への投稿。所有者が求めたときだけ）。
- CLI の `--minimum-release-age 7d`（手元の最新の bun が読む。Dependabot は読まない）。

## レビューの記録

### Codex 1 回目（2026-11-17）

| # | 指摘 | 判断 | 確認したこと |
|---|---|---|---|
| 1 | 「全 job が成功し週 1 の PR が開く」は完了の条件として広すぎ、無関係な失敗でも revert すると `"7d"` の失敗が戻る | 採用 | 完了の条件を bun の job の構文エラーが消えて完走することに絞り、revert はこの変更が原因と確かめたときだけにした |
| 2 | 引数なしの `just sync-agents` は `~/.claude` だけに配る。ほかのエージェントに古い例が残る | 採用 | `just sync-agents-preview all` で確かめてから `just sync-agents all` で配る手順にした |
