# 0060. 画像の凍結世代を 1 か所に持ち、install.sh の版本領域を生成する

**Date:** 2026-10-21
**Status:** Accepted
**ID:** ADR-0060
**Title:** 画像の凍結世代を 1 か所に持ち、install.sh の版本領域を生成する
**Decided-date:** 2026-10-21
**Decision-maker:** Hiroto N.
**Decision-maker-contact:** @hironow
**Author:** Pi（owner session）
**Author-contact:** @hironow
**Supersedes:** [ADR-0006](0006-mise-version-pinning.md) の一部（Decision 1 の「全 concrete pin」、Decision 3 の `mise use --system` と build-time check の形）。0006 の Status 行に後継を記した
**Superseded-by:** none
**Related:** [ADR-0006](0006-mise-version-pinning.md)、[ADR-0005](0005-install-path-rationalization.md)、[ADR-0027](0027-bun-only-retire-per-repo-pnpm-carveout.md)、[ADR-0036](0036-mise-npm-backend-bun.md)、[ADR-0040](0040-npm-args-inert-under-bun.md)、[ADR-0051](0051-adopt-decision-queue-for-new-records.md)
**Consultation-trace:** 本セッションでの所有者の選択（対象 = mise が持つ道具だけ / 画像の検証つき tarball の定数も含める / 正本は新規 1 ファイル / 生成器は Python の例外）→ 2026-10-21 に所有者が本セッションで裁定（Accepted）。計画は `docs/plan/mise-version-ssot.md`（独立レビュー #1〜#3 で APPROVE）。裁定の PR: [#485](https://github.com/hironow/dotfiles/pull/485)

## やさしい説明

同じ道具を、この repo は 2 つの場所へ入れる。ふだん使う機体（host）と、CI と IDE が使う devcontainer の画像である。
その 2 つは同じ版本を使うべきだが、画像はビルドのときに host の設定ファイルを読めない。だから画像の分は画像用に書く必要があり、これまでは install.sh の中に直接書かれていた。

そのため、**同じ道具の版が 2 か所に手で書かれ、片方だけ動いても誰も気づかなかった**。実際、画像の中の `uv` は 0.12.21 と 0.13.1、`just` は 1.58.0 と 1.59.0 の 2 つの版が同居していた（PATH の順で古い方は隠れていて、動いているように見えていた）。

この ADR は、画像の分の版を **1 つのファイル** に集め、install.sh の該当部分はそのファイルから **自動で書き出す**ことにする。人が install.sh を直接書き換えることはなくなり、片方だけ変える事故はコミットの時点で止まる。

## Context

- 2026-10-21 の実測: `config/mise/config.toml` は 37 道具、devcontainer が bake する `/etc/mise/config.toml` は 18 道具。重複する 18 のうち値まで一致するのは 3 つ（golangci-lint / quint / cf）だけで、他は「host は `latest`、画像は凍結版」という世代差だった。
- 画像は同じ道具を 2 経路で入れる。`.devcontainer/features/dotfiles-tools/install.sh` が検証つき tarball を `/usr/local/bin` に置き（`UV_VERSION="0.12.21"`、`JUST_VERSION="1.58.0"`、`SHELDON_VERSION="0.8.5"`）、`/etc/mise/config.toml` が mise で入れる（`uv = "0.13.1"`、`just = "1.59.0"`）。`devcontainer.json` の PATH は `/opt/mise/shims` が `/usr/local/bin` より先なので、実効版は mise 側。uv と just はこの 2 経路で食い違い、検査は無かった。
- `install.sh`（host の bootstrap）の `_just_ver="1.58.0"` も、`config/mise/config.toml` の `just = "latest"` が当時解決していた 1.59.0 と食い違っていた。
- ADR 0006 Decision 3 は「feature の hardcoded 定数と mise.toml の値は一致すること。実装 PR が build-time check で image build を落とす」と決めている。実際に存在したのは quint 1 件の一致テストだけで、一般の検査は無かった。
- mise は repo 内の `config/mise/config.toml` を project config として読まない（実測: そのパスを置いた dir で `mise config ls` が解決するのは `~/.config/mise/config.toml` だけ）。画像が見るのは bake した `/etc/mise/config.toml` のみ。

## Decision

1. **正本は `config/mise/image-tools.toml`**。画像が bake する mise 道具（`[tools]`）、検証つき tarball で入れる道具（`[fetch]`。mise 道具でもあるものは名前だけを書き、版は `[tools]` から取る）、mise が無い Linux 機体の bootstrap（`[bootstrap]`）を持つ。**版は道具ごとに 1 回だけ書く。**
2. **生成器は `scripts/mise_versions.py`（唯一の writer）**。`sync` が次の領域を書き、`check` が差分を報告する。
    - `.devcontainer/features/dotfiles-tools/install.sh`: `/etc/mise/config.toml` heredoc の本体、`UV_VERSION` / `JUST_VERSION` / `SHELDON_VERSION`
    - `install.sh`: `_mise_ver` / `_just_ver`
3. **検査を `lint` と `check` の両方に配線する**。pre-commit が呼ぶのは `just fmt` / `just lint` で、`just check` は pre-push 専用（既定で未インストール）なので、コミット時に止めるには `lint` が要る。
4. **検査は host との整合も見る**。`[tools]` と `[fetch]` の道具は `config/mise/config.toml` に存在し、host が exact pin の道具は値も一致すること（quint / golangci-lint / cf / sheldon）。`[bootstrap].mise` は host に無い（mise は mise 道具ではない）ので、比較先は `install.sh` の `_mise_ver` だけにする。
5. **生成器は Python**。`ROOT_AGENTS.md` は新しい services / CLIs / tools を Go とするが、これは配布物ではなく 2 つの tracked ファイルを書き換える repo のグルーで、同類の `scripts/bump_tool.py` も Python。TOML の読み書きは標準ライブラリ（`tomllib`）で済み、Go では新しい依存が要る。利用者の裁定（2026-10-21）により例外とする。
6. **画像の版は凍結のまま**（`latest` を画像で解決しない）。世代差は「別チャネル」として同じファイルに表現する。

## Consequences

### Positive

- 同じ道具の版はリポジトリ内で 1 か所になり、片側だけの bump は `just lint` / `just check` で止まる。
- ADR 0006 Decision 3 が約束した一致検査が実在するようになる（画像ビルドを待たず、コミット時と CI で分かる）。
- 画像の中の uv / just の二重取得が同じ版に揃う（PATH で隠れていた不一致が消える）。
- 版を上げる手順が「正本 1 行 → `just mise-versions-sync` → commit」になる。

### Negative

- install.sh の該当領域が生成物になる。直接編集するとチェックが落ちる（意図した挙動だが、`git blame` で版の履歴が install.sh に残らなくなる）。
- 生成器という新しい保守対象が増える（`tests/unit/test_mise_versions.py` が守る）。
- sheldon の per-arch SHA256 はハッシュであって版ではないので生成しない。sheldon を上げるときは正本 1 行 + install.sh 2 行の更新になる。

### Neutral

- `config/mise/config.toml` は今までどおり host の唯一の宣言で、手書きの理由コメントもそのまま。
- ruff / ty は対象外（3 か所にあるが `just bump-tool` が一括で動かす既存機構がある）。
- **所有者は、将来この生成器を Go で書き直したいという希望を持っている**（2026-10-21。今回は repo のグルーとして Python + 例外で入れ、`docs/plan/mise-version-ssot.md` の「対象外」に follow-up として記録した）

## 維持する事項 / 置き換える事項（ADR 0006 との関係）

**維持する**: 画像は検証つき取得（SHA + attestation）を通す（0006 Decision 3 前半）/ mise.lock を採らない（Strategy B の却下）/ `MISE_DATA_DIR=/opt/mise` の移設（Decision 4）/ 画像の `MISE_OFFLINE=1`（Decision 5）/ `config/mise/config.toml` が全 OS 共通の host 宣言であること。

**置き換える（すでに現行コードがそうなっている事実の追認を含む）**:

- **Decision 1「`= "latest"` を全部 concrete pin にする」** → 実際の host は、ゲートと再現性が要る道具は exact、それ以外は `latest` / `lts` で真の最新を追う。本 ADR はこの用途別方針を決定として記録し、host と画像の世代差を別チャネルとして扱う。
- **Decision 3「画像は `mise use --system` で検証済みバイナリを再利用する」** → 実際の画像は `/opt/mise` に通常の `mise install` で別コピーを入れ、検証つき tarball と併存する（install.sh に `mise use --system` は無い）。本 ADR はこの併存を決定として記録し、版の一致を生成で保証する。
- **Decision 3 の「build-time check で image build を落とす」** → 実現の形を変える。正本からの生成で不一致をそもそも作れなくし、コミット時（`just lint`）と CI（`just ci`）の drift 検査で止める。

裁定後、`docs/agents/docs-discipline.md` の規約どおり **ADR 0006 の Status 行だけ**を編集して部分置換を示す。

## 実機確認 (2026-10-21)

- `just mise-versions-sync` 前の RED: 新テストは 3 failed / 9 passed（drift 依存の 3 件）。sync 後に 12 passed。
- 生成の差分: `UV_VERSION` 0.12.21 → 0.13.1、`JUST_VERSION` 1.58.0 → 1.59.0、`_just_ver` 1.58.0 → 1.59.0。heredoc は道具の集合と値が同一（コメントが正本へ移り、生成ヘッダが付く）。
- 既存の install.sh 依存テスト 5 本（26 tests）は緑（heredoc の形と定数行を壊していない）。
- 負例: 正本だけ / host だけ / 生成領域 / `_mise_ver` の片側変更を、いずれも `check` が非ゼロで報告する。
- 画像側の tarball 取得（uv 0.13.1 の sha256 sidecar、just 1.59.0 の SHA256SUMS）は HTTP 200 を確認。実際の取得は CI の `Run just tests in dev container` で走る。
