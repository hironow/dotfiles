# Dependabot の clone ですべての submodule を飛ばす

**Date:** 2026-11-17
**Status:** 実装中（Codex のレビュー 2 回で指摘なし）
**Scope:** dotfiles のみ。worktree `../dotfiles-dependabot-submodules`、branch `fix/dependabot-skip-all-submodules`。
前の計画: `docs/plan/dependabot-private-submodule.md`（#633、merge 済み）。

## 何が起きたか（確認済みの事実）

- #633 で `knowledge-work-plugins` に `update = none` を付けた。merge の後（2026-11-16 16:31 UTC）、Dependabot は全エコシステムを再実行した。
- 9 件の job（github_actions、uv 3 件、bun、go_modules、docker、docker_compose、opentofu）が**すべて失敗した**。
  #633 の前は github_actions（と bun）だけが失敗していた。
- ログ（job 1709405958 ほか）:
    - `Skipping submodule 'knowledge-work-plugins'` が出ており、#633 の変更は効いている。
    - 続けて `fatal: No url found for submodule path 'protocols/UTCP/temp/openapi-directory' in .gitmodules` と `fatal: Failed to recurse into submodule path 'protocols/UTCP'` が出て、`Error during file fetching; aborting` で止まる。
- 原因: `protocols/UTCP` の pin（`4a9ed93`、2026-09-16）は、`.gitmodules` に載っていない gitlink `temp/openapi-directory` を持つ。上流の最新（同じ `4a9ed93`）も同じなので、pin を上げても直らない。
  #633 の前は private の submodule の失敗で git が再帰の前に止まっていたので、この壊れた入れ子まで届かなかった。
- 手元で気づかなかった理由: `just update-all-submodules` の 3 行目（`git submodule foreach ... 'git submodule update --init --recursive --checkout 2>/dev/null || true'`）がこのエラーを捨てている。
- Dependabot の clone の仕方（dependabot-core `common/lib/dependabot/file_fetchers/base.rb` の `_clone_repo_contents`）:
    - いつも `--no-tags --depth 1 --recurse-submodules --shallow-submodules` で clone する。設定で外す方法はない。
    - 失敗のうち許すのは `fatal: clone of '...' into submodule path '...' failed` と `fatal: unable to access ...` の 2 つだけ。ほかの失敗はそのまま raise して job を止める。
- 入れ子の gitlink を全 submodule について調べた。`.gitmodules` に載っていないのは `protocols/UTCP` の 1 つだけ。ほかの入れ子（`payments/x402` の 3 つ、`tools/tmux/plugins/tmux-resurrect` の 1 つ、`protocols/webmcp-tools` の 1 つ）は載っている。
- Dependabot の対象のディレクトリ（`/`、`/tools/rttm`、`/emulator`、`/emulator/*`、`/tests/docker`、`/telemetry`、`/tofu/tailnet`）はすべて本体の中にある。Dependabot は submodule の中身を使わない。
- CI の workflow は submodule を取らない（`claude-lint.yaml` と `pages.yaml` は `submodules: false`、ほかは既定の取らない設定）。

## 直し方の比較

| 案 | 内容 | 判断 |
|---|---|---|
| A | `protocols/UTCP` にも `update = none` を付ける | 不採用。直るのはこの 1 件だけ。34 個の submodule（大半は第三者の repo）のどれかが同じように壊れると、また全 job が止まる |
| B | **すべての** submodule に `update = none` を付ける | **採用**。Dependabot の clone は submodule を 1 つも取らなくなり、第三者の repo の状態に左右されない。Dependabot は submodule の中身を使わないので失うものはない |
| C | #633 を revert する | 不採用。前の状態（github_actions の失敗で週 1 の PR が出ない）に戻るだけ |

案 B の副作用（#633 で確かめた `update = none` の動きと同じ）:

- 所有者の checkout で、素の `git submodule update` と `--remote` は、すべての submodule を飛ばす。`--checkout` を付ければ今まで通り動く。
- `just update-all-submodules` と README の取得手順は #633 で `--checkout` 付きにしたので、そのまま動く。
- 変更の後に `git submodule init` した checkout には、`none` がローカルの `.git/config` に写る。

## 変更

1. **[Red]** `tests/unit/test_private_submodule_clone.py` を `tests/unit/test_dependabot_submodule_clone.py` に改名し（`git mv`、構造の変更として先に 1 commit）、次を足す（行動の変更として 2 つめの commit）。
   - 静的: `.gitmodules` の**すべての** submodule に `update = none` がある。
   - 準備: 再現の superproject に、公開役、private 役に加えて、**入れ子が壊れた役**（`.gitmodules` に載っていない gitlink を持つ repo。`git update-index --add --cacheinfo 160000,<sha>,temp/x` で作る）を足す。各役の `update` は、本物の `.gitmodules` の対応する submodule（公開役 = `protocols/A2A`、private 役 = `knowledge-work-plugins`、壊れた役 = `protocols/UTCP`）から読んで写す。
   - 対照: 設定を写さないとき、private 役が届く状態でも、壊れた役のために Dependabot と同じ clone が失敗する。stderr に `No url found for submodule path` と壊れた入れ子のパス（`broken/temp/x`）が出ることまで確かめる（ほかの理由の失敗で通らないように）。
   - 対照（#633 の状態）: private 役だけ `none` にしても、同じ `No url found` で失敗する。今回の退行をそのまま固定する。
   - private 役の対照（今あるもの）は残す。
   - 本題: 本物の設定を写すと、private 役を消した状態で clone が exit 0 になり、`git status --short` が空になる。公開役の中身は取らない（#633 のテストの「公開役の中身がある」は、この方針で外す）。
   - README の手順と `update-all-submodules` の行のテストは今のまま（`none` の submodule を取り、進める）。
2. **[Green]**
   - `.gitmodules`: すべての submodule に `update = none`（`git config -f .gitmodules submodule.<name>.update none` で足す）。
   - `.github/dependabot.yaml`: 理由のコメントを「private の 1 つ」から「すべて」に直し、`protocols/UTCP` の例を書く。この編集で merge 後に Dependabot が再実行される。
   - `justfile` の `update-all-submodules` の上のコメントと、README の 1 文を「すべての submodule」に直す。
   - `docs/plan/dependabot-private-submodule.md` の Status に、この計画で置き換えたことを書く。

## 確認（完了の定義）

- `just ci` が完走して成功する（時間制限を付けずに回す）。
- **merge の前に、本物のリポで Dependabot と同じ clone を確かめる。** branch を push したあと、所有者の git 設定から切り離して（`GIT_CONFIG_GLOBAL=/dev/null`、`GIT_CONFIG_NOSYSTEM=1`、`GIT_TERMINAL_PROMPT=0`、認証なし）、`git clone --no-tags --depth 1 --recurse-submodules --shallow-submodules --branch fix/dependabot-skip-all-submodules https://github.com/hironow/dotfiles <tmp>` を実行する。exit 0、`git status --short` が空、34 個の submodule がどれも取得されていない（`git submodule status` が全部 `-` で始まる）ことを確かめ、結果を PR に書く。#633 で抜けていたのはこの確認だった（合成の fixture と CI は通ったが、本物の全 submodule を Dependabot と同じ形で取る確認がなかった）。
- PR の CI が green。所有者の常設の許可に従って squash merge する。
- merge 後:
    - 手元の main を pull し、submodule の pin が変わらないこと、素の `git submodule update <path>` が飛ばし、`--checkout` 付きが動くことを確かめる（#633 と同じ確かめ方）。
    - Dependabot の再実行で、bun を除く **8 件の job がすべて success** になること。どれかが失敗したら、ログで次の原因を探し、同じ手順（計画、レビュー、再現テスト）で直す。
    - bun の job は別の原因で失敗し続ける見込み（下の「範囲外」）。週 1 の PR が開くのは、bun の件も直った後になる。
- 失敗したとき: この PR の squash commit を丸ごと revert する。変更の後に init した checkout では、`git config --get-regexp '^submodule\..*\.update$'` で `none` を探して `git config --unset` で消す。

## 範囲外

- **bun の job の失敗**（#633 の前の 14:36 の実行から。job 1709041923）。Dependabot の bun は `bunfig.toml` の `minimumReleaseAge = "7d"` を `Expected number of seconds for minimumReleaseAge` で拒む。`"7d"` の書き方はグローバルの spoke（`ROOT_AGENTS_docs_agents_web-ui.md`）と 2 つのテスト（`test_frontend_ci_conformance.py`、`test_web_ui_guidance.py`）が決めている。手元の bun 1.4.4 は数値の `604800` も受け付けた。グローバルのルールの変更になるので、所有者に伺ってから別の PR にする。

- `update-all-submodules` の 3 行目がエラーを捨てていること。入れ子の取得に失敗しても気づけないが、直すと `protocols/UTCP` のために recipe が毎回落ちる。所有者に報告だけする。
- Dependabot が出す PR の中身の確認。

## レビューの記録

### Codex 1 回目（2026-11-17）

| # | 指摘 | 判断 | 確認したこと |
|---|---|---|---|
| 1 | 合成の fixture と CI だけでは、本物の全 submodule を Dependabot と同じ形で取る確認が merge の後まで無い（#633 の穴） | 採用 | push した branch を GitHub から Dependabot と同じコマンドで clone する確認を、merge の前の必須条件にした |
| 2 | 壊れた入れ子の対照は、失敗の理由（`No url found` と入れ子のパス）まで確かめる。#633 の状態の対照も置く | 採用 | 変更 1 の対照を 2 つに分け、stderr の中身を確かめる形にした |
