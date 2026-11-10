# ADR 0071 — Rust の clippy を、出荷する target ごとに回す

- **id**: ADR-0071
- **title**: Rust の clippy を、出荷する target ごとに回す
- **status**: Proposed
- **date**: 2026-11-11
- **decided-date**: —
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code（owner session、Windows 機）
- **author-contact**: @hironow
- **supersedes**: none（ADR-0069 が「決めていない」とした Rust の分を決める）
- **superseded-by**: none
- **related**: [0052](0052-renew-global-agent-instructions.md)、[0069](0069-type-check-and-lint-for-every-os.md)
- **consultation-trace**: 2026-11-11 の本セッションでの所有者の選択（下の「相談の記録」）。同じ内容を公開 PR に残す

## やさしい説明

Rust の lint（clippy）は、確かめる対象の OS と CPU（target）の分岐しか見ない。
そのため、Windows や macOS でだけ動く部分の誤りが残ることがある。
これからは、出荷する target ごとに clippy を回すよう、全 agent が読む規則に書く。

## Context

- ADR-0069 は、ty と golangci-lint を、コードが動く OS ごとに回すと決めた。Rust の clippy は「決めていない（別に提案する）」とした（0069 の Options C と Neutral）。
- rust-tooling の spoke は、clippy を手元の target で 1 回だけ回し、出荷は OS と CPU ごとと書いていた。ADR-0052 の Decision 1 は「OS と CPU ごとに 1 つのバイナリ」。
- 2026-11-10 に GitHub Actions の Linux・Windows・macOS の runner で測った（rustup 1.29.2/1.29.3、rustc 1.99.1、4 つの target: x86_64-unknown-linux-musl、aarch64-unknown-linux-musl、aarch64-apple-darwin、x86_64-pc-windows-msvc）。
    - C を build しない crate: どの機体からでも 4 つとも通った（target のコードは link しない）。
    - `#[cfg(target_os = "macos")]` の下の clippy の誤り（`eq_op`）: `--target aarch64-apple-darwin` でだけ見つかった。どの機体からでも同じ。
    - target 向けに C を build する依存（`ring` 0.17）: その OS の target でだけ通った（Windows の機体は windows-msvc、macOS の機体は darwin）。Linux の機体は linux-musl でも `musl-gcc` が無く通らなかった。
    - `cargo clippy` に `--target` を何回も渡すこともできた。
- この Windows 機では mise が `RUSTUP_TOOLCHAIN` を設定するので、rustup は `rust-toolchain.toml` を読まない（toolchain も targets も）。toolchain の lib には x86_64-pc-windows-msvc しか無かった。

## Decision

（Proposed。確定後に MUST 文で記述。）

決定案:

- D1: rust-tooling の spoke の `rust-lint` は、出荷する target ごとに `cargo clippy --all-targets --all-features --target <triple> -- -D warnings` を回す。target の一覧は justfile の `rust_targets` に 1 か所だけ置き、release の build も同じ一覧を使う。recipe は shebang と `set -euo pipefail` を持ち、`rustup target add` を自分で行う（`rust-toolchain.toml` の targets に頼らない）。
- D2: 出荷するどの target の clippy も、merge を止める gate のどこかで回る。target 向けに C を build する依存があって手元で回せない target は、その OS の CI のジョブで `just rust-lint <triple>` を回し、どのジョブがどの target を見るかを justfile に書く。target を黙って外さない。
- D3: `-D warnings` で、別の target でだけ使われない helper は、同じ `#[cfg(...)]` を付けるか `if cfg!(...)` で書く。`#[allow(dead_code)]` で隠さない。
- D4: lint はその OS での動きを証明しない。動きはその OS でテストを回して確かめる、と spoke に書く。

## Options Considered

| 案 | 利点 | コスト・リスク |
| --- | --- | --- |
| A) 出荷する target ごとに clippy を回す（本案） | Windows・macOS だけの lint の誤りを、その OS の機体なしで止められる（C を build しない crate） | Rust の repo の `just check` が target の数だけ長くなる。C を build する依存がある crate は、その OS の CI が要る |
| B) 今のまま手元の target だけ | 変更が無い | ADR-0069 で Go と Python から外した見逃しが、Rust にだけ残る |

## Consequences

- **Positive**: Go・Python・Rust の 3 つで、別の OS の分岐の型と lint の誤りを、gate が見るようになる。
- **Negative**: `just check` が target の数だけ長くなる。C を build する依存がある crate は、手元で見られない target をその OS の CI で回す必要がある。
- **Neutral**: dotfiles には Rust のコードが無いので、変わるのは spoke とテストだけ。spoke の「`rust-toolchain.toml` で toolchain を pin する」は、mise が `RUSTUP_TOOLCHAIN` を設定する機体では効かない。これはこの ADR の前からの問題で、ここでは決めない（handover に残す）。

## 反転記録 (Reversal)

- 反転はない。ADR-0069 の「Rust の clippy は決めていない」を、この ADR が決める（0069 は変えない）。

## 他の DR との照合

0001〜0070 の 69 件（0046 は欠番）の題名・状態・置換関係を走査し、Rust・lint・cross-OS・出荷に触れる記録の全文を読んだ（0052、0069 ほか）。PDR はない。

- **矛盾**: なし。0069 の Neutral と Options C が予告した後続にあたる。
- **重複**: 番号 0071 は未使用。同じ決定の記録はない。
- **誤読**: 0069 は Rust を「採らない」とは決めておらず、「決めていない（別に提案する）」とした。
- **偽の関連**: 0052 の Decision 1（OS と CPU ごとのバイナリ）は D1 の根拠で、衝突しない。
- **関係誤認**: 0069 を置き換えない（`supersedes: none`）。

## 相談の記録

- 2026-11-11、本セッションで所有者（@hironow、0052・0069 の決定者）が、上の実測を見たうえで A を選んだ。
- 計画は独立サブエージェントがレビューした（Codex はクレジット切れ）。`rust-toolchain.toml` の targets が読まれないこと、C を build する crate の扱い、実測の不足、recipe を just で確かめること、cfg の付いたコードの直し方を、その指摘から採った。

## 決定（記入待ち）

- [ ] A を Accepted（D1〜D4 を MUST 文で確定し、索引、変更ログ、queue を更新する）
- [ ] B を Accepted（spoke の変更を戻し、「Rust は手元の target だけ」と記録する）
- [ ] Rejected / Deferred（変更を戻し、queue に理由を残す）

決定者: ＿＿＿　決定日: ＿＿＿
