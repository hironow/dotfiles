# ADR 0070 — native Windows では pnpm を用意しない

- **id**: ADR-0070
- **title**: native Windows では pnpm を用意しない
- **status**: Accepted
- **date**: 2026-11-10
- **decided-date**: 2026-11-10
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code（owner session、Windows 機）
- **author-contact**: @hironow
- **supersedes**: ADR-0017 の「pnpm は repo ごとに corepack で用意する」のうち native Windows の分、ADR-0018 の `step_corepack` の Windows 枝（`corepack enable` を実行する）
- **superseded-by**: none
- **related**: [0017](0017-retire-pnpm-global-for-corepack.md)、[0018](0018-windows-native-mvp.md)、[0027](0027-bun-only-retire-per-repo-pnpm-carveout.md)、[0031](0031-disable-mise-corepack-on-windows.md)、[0039](0039-windows-bootstrap-ps1.md)、[0066](0066-doctor-warns-only-what-needs-action.md)
- **consultation-trace**: 2026-11-10 の本セッションでの所有者の指示と選択（下の「相談の記録」）。同じ内容を公開 PR に残す

## やさしい説明

pnpm（Node のパッケージを入れる道具の一つ）は、Windows の機体では使わない。
これまで Windows でも用意しようとしていて、`just doctor` は「無い」と警告していた。
Windows では用意せず、警告もしないようにする。macOS と Linux は今のまま。

## Context

- 2026-11-10、所有者が「Windows では pnpm が不要」と指示した。
- ADR-0017 は、pnpm を repo ごとに corepack（Node に付いてくる、パッケージマネージャーを用意する道具）で用意すると決めた。ADR-0018 は、native Windows でも `install.sh` の `step_corepack` で `corepack enable`（pnpm の shim を作る）を実行すると決めた。
- ADR-0027 は、agent が npm・yarn・pnpm を使うことを禁じた（Node は bun だけ）。その Neutral は、doctor の pnpm の行を「将来の provisioning を外す ADR」に回している。
- ADR-0031 は、Windows で mise の corepack の自動実行を止めた（`MISE_NODE_COREPACK=0`）。
- node 26（2026-10-28 から LTS）は corepack を同梱しない。この Windows 機の node 26.13.0 の install dir に corepack は無い。`install.sh` は `set -eu` で動くので、Windows では `step_corepack` の `mise exec -- corepack enable` が失敗し、dotfiles の symlink の段まで進まない。
- この Windows 機の `just doctor` の WARN の 1 つが `pnpm - missing` だった。

## Decision

A 案の次の 4 項を、必須事項（MUST）として採択する。

- D1: native Windows では pnpm を用意してはならない（MUST NOT）。`install.sh` の `step_corepack` の Windows 枝は、理由を付けて飛ばさなければならない（`_skip_windows`）。
- D2: `just doctor` は native Windows では pnpm の行を出してはならない。macOS・Linux・WSL では今までどおり確かめなければならない（MUST）。
- D3: `bootstrap.ps1` は npm・yarn・pnpm・corepack を呼んではならない（MUST NOT）。テストがこれを止める。
- D4: macOS・Linux・WSL・dev container の corepack による供給、`PNPM_HOME`、global CLI を mise の npm: で入れること（ADR-0017）は変えない。

## Options Considered

| 案 | 利点 | コスト・リスク | 裁定 |
| --- | --- | --- | --- |
| A) doctor と install.sh の両方で、native Windows の pnpm をやめる（本案） | 警告が消え、Windows の install.sh が corepack で止まらなくなる | Windows で pnpm を使う repo を手で扱う場合は、各自で用意する | 所有者が採択 |
| B) doctor の警告だけ消す | 変更が最小 | install.sh は Windows でも corepack enable を試み続け、node 26 では失敗して止まる | install.sh が止まる問題が残るため却下 |

## Consequences

- **Positive**: native Windows の doctor から、手の打ちようのない WARN が消える。Windows の `install.sh` が `step_corepack` で止まらない。
- **Negative**: native Windows で pnpm を前提にする repo は、この dotfiles では用意されない（agent は ADR-0027 でそもそも使わない）。
- **Neutral**: WSL は今 node 24.22.1 で corepack があるので、pnpm の確認は今のまま。node が 26 に上がれば WSL でも `pnpm - missing` が出るが、WSL を含む他の OS はこの ADR の範囲外で、別に決める。ADR-0031 の決定（`MISE_NODE_COREPACK=0`）はそのまま残り、その open item（`mise exec -- corepack enable` が EPERM するか）はこの ADR で問う必要がなくなる。

## 反転記録 (Reversal)

- ADR-0017 の「pnpm は repo ごとに corepack で用意する」を、native Windows では適用しない。macOS・Linux・WSL・dev container の供給、`PNPM_HOME`、mise の npm: は反転しない。
- ADR-0018 の `step_corepack` の Windows 枝（実装して `corepack enable` を実行する）を、`_skip_windows` に替える。explicit-skip の設計と deploy の subset は反転しない。
- 旧 ADR は決定本文を変えず、採択時に Status 行で部分置換を示す。

## Enforcement inventory

native Windows の入口:

- `install.sh` の `step_corepack`（`_skip_windows`。`tests/unit/test_install_os_dispatch.py` が固定）
- `scripts/doctor.sh` の pnpm の行（native Windows では出さない。`tests/unit/test_doctor_os_gating.py` が固定）
- `bootstrap.ps1`（npm・yarn・pnpm・corepack を呼ばない。`tests/unit/test_bootstrap_ps1.py` が固定）
- `scripts/deploy.sh` の `$PROFILE` の `MISE_NODE_COREPACK=0`（ADR-0031。corepack を止める側なので維持）
- `config/mise/config.toml` の `[settings.node] corepack = true`（Windows では上の env で無効）

## 他の DR との照合

0001〜0069 の 68 件（0046 は欠番）の題名・状態・置換関係を走査し、Node・pnpm・corepack・Windows の導入・doctor に触れる記録の全文を読んだ（0017、0018、0027、0031、0033、0036、0039、0040、0066 ほか）。PDR はない。

- **矛盾**: 0017（pnpm を corepack で用意）と 0018（Windows の `step_corepack` を実装）の Windows の分。所有者が 2026-11-10 にこの範囲を選んだ（下の「相談の記録」）。
- **重複**: 番号 0070 は未使用。同じ決定の記録はない。
- **誤読**: 0031 は mise の corepack の自動実行を止めるもので、`corepack enable` そのものを決めたものではない。この ADR と矛盾しない。
- **偽の関連**: 0027 は agent の利用を禁じる層で、機体への供給は 0017 のまま。この ADR は 0027 の Neutral が予告した後続にあたる。0036・0040 は mise の npm backend で、関係しない。0066（Proposed）の「その OS に合わない行は出さない」と同じ向き。
- **関係誤認**: 0017 と 0018 を丸ごと失効させない。Status 行に範囲を限った部分置換を書く。

## 相談の記録

- 2026-11-10、本セッションで所有者（@hironow、0017・0018・0027・0031 の決定者）が「Windows では pnpm が不要」と指示した。
- 計画の独立レビュー（Claude サブエージェント、Codex はクレジット切れ）が、doctor だけでは足りず install.sh が Windows で corepack enable を実行していることを見つけた。所有者は範囲として A（doctor と install.sh）を選び、決定欄への代理記入を認めた。

## 決定（2026-11-10）

- [x] A を Accepted（D1〜D4 を MUST 文で確定し、0017・0018 の Status 行、索引、変更ログ、queue を更新する）
- [ ] B を Accepted（install.sh の変更を戻し、doctor だけにする）
- [ ] Rejected / Deferred（変更を戻し、queue に理由を残す）

決定者: Hiroto N.（@hironow）　決定日: 2026-11-10（所有者の選択により代理記入）

- B 案は install.sh が node 26 の Windows で止まる問題が残るため却下する。
- 採択時に 0017・0018 の Status 行、索引、変更ログ、queue の決定済みログを同時に更新し、旧本文を変えていないことを確かめた。
