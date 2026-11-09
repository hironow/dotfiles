# ADR 0069 — 型検査と lint を、コードが動く OS ごとに回す（ty と golangci-lint）

- **id**: ADR-0069
- **title**: 型検査と lint を、コードが動く OS ごとに回す（ty と golangci-lint）
- **status**: Accepted
- **date**: 2026-11-10
- **decided-date**: 2026-11-10
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code（owner session、Windows 機）
- **author-contact**: @hironow
- **supersedes**: ADR-0044 の Decision 1 のうち、雛形の `just lint` が ty を 1 回回すという記述（OS ごとに回す形へ拡張）
- **superseded-by**: none
- **related**: [0044](0044-python-toolchain-uv-ruff-ty.md)、[0050](0050-pin-go-sources-to-lf.md)、[0052](0052-renew-global-agent-instructions.md)、[0068](0068-pin-the-dev-container-mise.md)、PR [#576](https://github.com/hironow/dotfiles/pull/576)・[#583](https://github.com/hironow/dotfiles/pull/583)
- **consultation-trace**: 2026-11-10 の本セッションでの所有者の指示（下の「相談の記録」）。同じ内容を[公開 PR #586](https://github.com/hironow/dotfiles/pull/586) に残す

## やさしい説明

型の検査と lint（コードの誤りを機械で見つける道具）は、検査している機体の OS の分岐しか見ない。
そのため、Linux で緑でも、Windows でだけ動く部分の誤りが残ることがあった。
これからは、コードが動く OS ごとに検査を回す。全 agent が読む規則と、新しい repo の雛形にこれを書く。

## Context

- 2026-11-09、Linux で緑の `just check` が、Windows でだけ出る ty の誤り 32 件と、使われない Go の関数 3 件を見逃した（[#576](https://github.com/hironow/dotfiles/pull/576) で修正）。
- ty は、検査する OS（`--python-platform`、既定は動いている機体）に合わせて `sys.platform` と `os.name` を決め打ちし、分岐を絞り込む。2026-11-10 に ty 0.0.91 で確かめた：win32 では `os.name` が `Literal["nt"]`、linux と darwin では `Literal["posix"]`。
- OS の条件の下で import した名前は、別の OS の検査では存在しない。注釈に使うと誤り、本体で使った所は検査されない（同じ日の実験。#576 の 18 件はこれ）。標準ライブラリの OS 専用モジュール（`pwd`、`grp`、`fcntl` など）は、typeshed が中身を `sys.platform` で分けているので、`TYPE_CHECKING` の下でも別の OS では中身が無い。
- golangci-lint は 1 回の実行で 1 つの GOOS 向けにしか build しない。build tag の付いたファイルと、そこからしか呼ばれないコードは、別の GOOS では検査されず、使われないと報告される。
- [#583](https://github.com/hironow/dotfiles/pull/583) で、dotfiles の `just check` は ty を win32 / linux / darwin で、golangci-lint を GOOS windows / linux / darwin で回すようにした。この機体で `just check-ty`（3 回）は約 1 秒、`just go-lint`（13 モジュール × 3）は約 63 秒だった。CI の dev container ジョブでは golangci が `just check` 1 回あたり約 5 分増えた。
- global の規則（`ROOT_AGENTS_docs_agents_python-tooling.md` と `go-tooling.md`）と雛形（`templates/agent-baseline/justfile`）は、ty と golangci を 1 回だけ回すと書いていた。ADR-0044 の Decision 1 は、雛形の `just lint` を「ruff check と ty check」と記録している。
- hub（AGENTS.md）は Go について「OS と CPU ごとに 1 つのバイナリを出す」と書く。

## Decision

A 案の次の 4 項を、必須事項（MUST）として採択する。

- D1: Python のプロジェクトの全体の gate（`just check`）は、コードが動く OS ごとに `ty check --python-platform <os>` を回さなければならない（MUST）。開発者の機体で動く道具は win32 / linux / darwin の 3 つ、Linux にだけ置くサービスは linux だけとする。行を消してよいのは、その OS で決して動かないときだけで、誤りを隠すために消してはならない。
- D2: Go のプロジェクトの `go-lint` は、出荷する OS ごとに `GOOS=<os> golangci-lint run` を回さなければならない（MUST）。`fmt --diff` は 1 回でよい。recipe は shebang と `set -euo pipefail` を持ち、どの GOOS の失敗でも止まらなければならない。
- D3: python-tooling の spoke は、OS の分岐（`sys.platform` で書く）、OS 専用の import（自前のモジュールは `TYPE_CHECKING or sys.platform` の下、標準ライブラリのものは同じ関数の `sys.platform` の確認のあとでだけ使う）、OS で飛ばすテスト（本体で `pytest.skip`）、別の OS でしか入らない依存（止めて人に聞く）の書き方を示さなければならない（MUST）。雛形の `lint` は spoke の例と同じ行でなければならず、テストがその一致を保つ。
- D4: spoke は、型検査と lint がその OS での動きを証明しないこと、動きはその OS でテストを回して確かめることを示さなければならない（MUST）。

## Options Considered

| 案 | 利点 | コスト・リスク | 裁定 |
| --- | --- | --- | --- |
| A) global の規則と雛形で、OS ごとに回す（本案） | どの repo でも、Windows・macOS だけの誤りを、その OS の機体なしで止められる | 全体の gate で ty が 2 回、golangci が GOOS の数だけ増える。別の OS でしか入らない依存があると、人の判断が要る | 所有者が採択 |
| B) dotfiles だけで回し、global の規則は変えない（#583 の状態） | 変更が最小 | 雛形から作った repo と他の repo では、同じ見逃しが続く | 他の repo で見逃しが続くため却下 |
| C) A に加え、Rust の clippy も target ごとに回す | 3 つの言語がそろう | 所有者の指示は ty と golangci が対象。Rust は target の追加（`rustup target add`）や C を build する crate の扱いが別に要る | 今回は採らない。Rust は別に提案する |

## Consequences

- **Positive**: 型の誤りと使われない Go のコードを、その OS の機体なしで見つけられる。雛形と spoke の例が同じ行に保たれる。
- **Negative**: 全体の gate が長くなる（ty は 1 回 1 秒程度で小さい。golangci は GOOS の数だけ型検査をやり直す）。雛形の pre-commit は `just check` を回すので、commit も ty 2 回分長くなる。別の OS でしか入らない依存は、そのままでは解決できず、人の判断が要る。
- **Neutral**: dotfiles 自身は、pre-commit の `just lint` で ty を 1 回、`just check` で 3 回回す（repo の CLAUDE.md に例外として記録）。Rust の clippy を target ごとに回すかは決めていない（別に提案する）。hub（ROOT_AGENTS.md と ROOT_CLAUDE.md）は変えない。

## 反転記録 (Reversal)

- ADR-0044 の Decision 1 の「雛形の `just lint` = ruff check と ty check」を、ty を OS ごとに回す形に広げる。uv・ruff・ty の 3 つにそろえる決定、mise での宣言、版の固定は反転しない。
- 旧 ADR は決定本文を変えず、採択時に Status 行で部分置換を示す。

## 他の DR との照合

0001〜0068 の 67 件（0046 は欠番）の題名・状態・置換関係を走査し、Python と Go の道具、検査の gate、雛形、Windows に触れる記録の全文を読んだ（0018、0020、0039、0044、0050、0052、0061、0067、0068 ほか）。PDR はない。

- **矛盾**: 0044 の Decision 1 の雛形の記述（ty 1 回）。0044 の決定者である所有者が、2026-11-10 にこの拡張を指示した（下の「相談の記録」）。
- **重複**: 番号 0069 は未使用。同じ決定の記録はない。
- **誤読**: 0050 は Go のソースの改行（LF）を決めたもので、検査の回数とは別。
- **偽の関連**: 0052 の Decision 1（Go を優先、OS と CPU ごとのバイナリ）は D2 の根拠で、衝突しない。0068 は画像の mise の取得で、関係しない。
- **関係誤認**: 0044 を丸ごと失効させない。Status 行に範囲を限った部分置換を書く。

## 相談の記録

- 2026-11-10、本セッションで所有者（@hironow、0044・0052 の決定者）が、「OS ごとの ty と golangci の検査を、global の規則と新しい repo 用の雛形にも入れますか」に「YES」と答えた。
- 2026-11-10、所有者が A を選んだ（「Aで」）。決定欄への記入は、0068 と同じく代理で行った。
- 計画は独立サブエージェントが 2 回レビューした（Codex はクレジット切れ）。範囲を「コードが動く OS ごと」にすること、Rust を対象外にして ADR の題を ty と golangci に限ることは、そのレビューの指摘を採った。

## 決定（2026-11-10）

- [x] A を Accepted（D1〜D4 を MUST 文で確定し、0044 の Status 行、索引、変更ログ、queue を更新する）
- [ ] B を Accepted（spoke と雛形の変更を戻し、queue に理由を残す）
- [ ] C を Accepted（Rust の rust-tooling の spoke も同じ PR で変える）
- [ ] Rejected / Deferred（変更を戻し、queue に理由を残す）

決定者: Hiroto N.（@hironow）　決定日: 2026-11-10（所有者の選択により代理記入）

- B 案は他の repo で見逃しが続くため却下する。C 案（Rust）は今回の範囲に入れず、別に提案する。
- 実装は [PR #586](https://github.com/hironow/dotfiles/pull/586)。採択時に 0044 の Status 行、索引、変更ログ、queue の決定済みログを同時に更新し、0044 の本文を変えていないことを確かめた。
