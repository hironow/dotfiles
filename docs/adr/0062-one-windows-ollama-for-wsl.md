# 0062. 共存機の Ollama は Windows の Scoop ollama-full に 1 台だけ置き、WSL はクライアントにする

**Date:** 2026-10-25
**Status:** Accepted
**ID:** ADR-0062
**Title:** 共存機の Ollama は Windows の Scoop ollama-full に 1 台だけ置き、WSL はクライアントにする
**Decided-date:** 2026-10-25
**Decision-maker:** Hiroto N.
**Decision-maker-contact:** @hironow
**Author:** Claude Code（owner session）
**Author-contact:** @hironow
**Supersedes:** [ADR-0058](0058-pi-web-search-ollama.md) の一部（Decision 4 の全体と、Decision 3 の Windows・WSL での適用）。0058 の Status 行に後継を記した
**Superseded-by:** none
**Related:** [ADR-0058](0058-pi-web-search-ollama.md)、[ADR-0035](0035-runner-disk-gc.md)、[ADR-0063](0063-declared-tailnet-forward-of-ollama.md)、[ADR-0064](0064-mirrored-wsl-uses-the-shared-loopback.md)、[runbook](../runbook/ollama-windows-wsl.md)、[PR #502](https://github.com/hironow/dotfiles/pull/502)
**Consultation-trace:** DR 間整合検査で、ADR-0058 の Decision 3・4 と PR #502 の実装の矛盾を検出した。所有者が 2026-10-25 の本セッションで「別の ADR で置き換える」と裁定し、裁定は [PR #504 の所有者裁定（明示許可による代理記録）](https://github.com/hironow/dotfiles/pull/504#issuecomment-6400086305) に記録した。

## やさしい説明

Windows と WSL が同じ機体にある時（共存機）、Ollama の本体は Windows 側に 1 つだけ置く。
モデルとログインの情報も Windows 側に置く。
WSL には Ollama を入れず、Windows の本体をクライアントとして使う。
この形は 2026-10-25 に merge した PR #502 で入った。
それまでの記録（ADR-0058）は「WSL 側に 1 台」だったので、この記録で置き換える。

## Context

- ADR-0058（2026-10-19）の Decision 4 は、共存機では Ollama を WSL 側に 1 台だけ置き、Windows 側の bootstrap は入れないと決めた。
- ADR-0058 の Decision 3 は、Ollama が無く `localhost:11434` も答えない時に、公式の導入手順で入れると決めた。
- ADR-0058 の Negative は、WSL 側に置くと Windows 側の利用が WSL の稼働に縛られ、モデルが WSL の disk に置かれて [ADR-0035](0035-runner-disk-gc.md) の vhdx の容量の圧力が増えると記している。
- PR #502（2026-10-25 merge）は、Windows の Scoop `extras/ollama-full` を唯一の本体にした。WSL には管理対象の CLI の口とブリッジを置き、Linux 版は入れない。`scripts/install_pi_extensions.py` は Windows と WSL では `scripts/ollama_host.py --setup` に任せ、公式の導入手順に戻らない。`just doctor` が、唯一の本体であること、重複、公開を検査する。
- #502 は ADR-0058 を置き換える記録を残さなかった。そのため、記録上の決定と実装が逆になっていた。

## Decision

1. 共存機の Ollama の本体は、Windows の Scoop `extras/ollama-full` の 1 つだけとしなければならない（MUST）。モデルと認証の情報も Windows 側に置く。
2. WSL には、Ollama の本体（Linux 版の binary、package、process、service）とモデルを置いてはならない（MUST NOT）。WSL は管理対象のクライアント（`~/.local/bin/ollama`）と、網の形に応じた経路（NAT ならブリッジ、mirrored なら共有の loopback。[ADR-0064](0064-mirrored-wsl-uses-the-shared-loopback.md)）で Windows の本体を使う。
3. Windows と WSL では、`scripts/install_pi_extensions.py` は Ollama の公式の導入手順を使わず、`scripts/ollama_host.py --setup` に任せなければならない（MUST）。WSL のない Linux と macOS は ADR-0058 Decision 3 のままとする。
4. 本体の所有、重複、公開の判定は `scripts/ollama_host.py --check`（`just doctor`）が行う。手順と判定の詳細は [runbook](../runbook/ollama-windows-wsl.md) を正とする。

## Options Considered

| 案 | 利点 | コスト・リスク | 所有者の選択 |
| --- | --- | --- | --- |
| Windows 側に 1 台（#502） | Windows の native の GPU とモデルを直接使う。WSL の停止に縛られない。モデルが vhdx を圧迫しない | WSL からの経路（ブリッジまたは共有の loopback）の管理と検査が要る | 選択済み（#502 の merge と本裁定） |
| WSL 側に 1 台（ADR-0058 Decision 4） | NAT の既定で Windows から localhost で届く | Windows 側の利用が WSL の稼働に縛られ、モデルが vhdx を圧迫する（ADR-0058 の Negative） | 不採用 |
| 両側に 1 台ずつ | どちらの側も単独で動く | 同じ 11434 とモデルの置き場が 2 つになり、どちらが答えたかを判定できない | 不採用 |

## Consequences

### Positive

- 記録と実装が一致し、共存機の Ollama の置き場所を 1 か所で説明できる。
- WSL に Ollama やモデルが残っていれば、doctor が ERR で示す。

### Negative

- Windows の本体が止まると、WSL からも使えない。WSL で代わりの `ollama serve` を起こさない。
- WSL からの経路を網の形ごとに持つ必要がある（[ADR-0064](0064-mirrored-wsl-uses-the-shared-loopback.md)）。

### Neutral

- ADR-0058 の Decision 1・2（Pi の web 検索の一本化と計測の停止）と、WSL のない Linux・macOS での Decision 3 は変えない。
- Scoop の宣言（`dump/windows/scoop.json`）と復元の仕組み（[ADR-0032](0032-windows-scoop-restore-add-scoop.md)）は変えない。

## 反転記録 (Reversal)

- 旧: ADR-0058 Decision 4「共存機では Ollama を WSL 側に 1 台だけ置く」。
- 新: Windows の Scoop `extras/ollama-full` に 1 台だけ置き、WSL はクライアントにする。
- 旧: ADR-0058 Decision 3 の「Ollama が無ければ公式の手順で入れる」を、Windows と WSL にも当てはめること。
- 新: Windows と WSL では `scripts/ollama_host.py --setup` に任せ、公式の手順に戻らない。WSL のない Linux と macOS では Decision 3 を維持する。
- 元記録の決定者と作者の連絡先はどちらも `@hironow`。所有者が本セッションで置き換えを裁定し、公開 PR への代理記録を許可した。

## 他の DR との照合

全 60 件（0001〜0045、0047〜0061。0046 は存在せず、PDR なし）の見出しと状態を走査した。
Ollama、WSL、mirrored、Tailscale、tailnet、Funnel、11434、loopback で候補を絞り、0005、0018、0032、0035、0037、0039、0048、0058、0059 を読んだ。
ADR-0058 の Decision 3・4 との矛盾を検出し、所有者が置き換えと裁定した（上の Consultation-trace）。
ADR-0032 は Scoop の宣言の読み方を決めた記録で、当時の宣言の中身として `ollama` を挙げているだけであり、どの Ollama を使うかは決めていない。矛盾ではない。
ADR-0059 は ADR-0058 を関連として挙げるだけで、Ollama の置き場所は決めていない。
その他の衝突は検出していない。

## 決定（2026-10-25）

- **Accepted**。決定者: Hiroto N.（@hironow）。本セッションでの所有者の裁定を、[PR #504 の所有者裁定（明示許可による代理記録）](https://github.com/hironow/dotfiles/pull/504#issuecomment-6400086305)。
- ADR-0058 は Status 行だけを更新し、本文は変えない。
