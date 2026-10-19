# 0058. Pi の web 検索を Ollama 経由に寄せ、pi 本体の計測を全機体で止める

**Date:** 2026-10-19
**Status:** Accepted
**ID:** ADR-0058
**Title:** Pi の web 検索を Ollama 経由に寄せ、pi 本体の計測を全機体で止める
**Decided-date:** 2026-10-19
**Decision-maker:** Hiroto N.
**Decision-maker-contact:** @hironow
**Author:** Pi（owner session）
**Author-contact:** @hironow
**Supersedes:** none
**Superseded-by:** none
**Related:** [ADR-0056](0056-common-claude-plugin-set.md)、[ADR-0057](0057-shared-plugins-need-no-per-home-settings.md)、[ADR-0049](0049-headroom-mandatory-base-tooling.md)
**Consultation-trace:** 本セッションでの所有者の直接指示（pi web search extension の入れ替え・計測の確認・Ollama 導入）

## やさしい説明

Pi（この dotfiles が管理する coding agent）で web 検索を使う extension を、Ollama 製のものに取り替えた。
Pi 本体が勝手に送っていた匿名の計測も、全機体で送らないように設定に書いた。
web 検索の新しい extension はローカルの Ollama がないと動かないので、なければ公式の手順で入れるようにした。

## Context

`dump/harness/pi-packages.json`（Pi の extension package の宣言。ADR-0056 の plugin 宣言と同じ役割）には、web 系 extension として `npm:pi-web-access` が入っていた。

2026-10-19 に、`npm:@ollama/pi-web-search` を入れたところ、Pi の起動が次のエラーで失敗した。

> Tool "web_search" conflicts with pi-web-access/dist/index.js

両方とも同名の `web_search` tool を登録するため、Pi は 2 つ目のロードを拒否する。どちらか一方しか使えない。

同じ日に、Pi 1.3.0 の配布物（`settings-manager.js`・`telemetry.js`・`interactive-mode.js`）で計測の実装を確認した。

- `enableInstallTelemetry` は default が **true** で、install・update のたびに `https://pi.dev/api/report-install?version=<version>` へ User-Agent `pi/<version> (<platform>; <runtime>; <arch>)` を送る。中身は版と実行環境の情報のみ。
- `enableAnalytics` は default が false（opt-in）。
- 環境変数の上書きは `PI_TELEMETRY` だけ。この dotfiles の各 shell が export している `DO_NOT_TRACK=1` を Pi は読まない。
- この時点で `~/.pi/agent/settings.json` にこれらの key はなく、install report は匿名で送られていた。

新しい extension は `http://localhost:11434` の Ollama（`/api/experimental/web_search`）に無認証で接続する。API key の類はなく、Ollama 本体がその機体にないと動かない。Ollama 公式の download page（<https://ollama.com/download）は> 2026-10-19 時点で macOS・Linux に `curl -fsSL https://ollama.com/install.sh | sh`、Windows（PowerShell）に `irm https://ollama.com/install.ps1 | iex` を示している（install.sh は macOS と Linux 両方に対応し、macOS では /Applications への app 導入と `ollama` command の symlink まで行う）。

## Decision

1. Pi の web 系 extension は `npm:pi-web-access` をやめ、`npm:@ollama/pi-web-search` に一本化する。宣言は `dump/harness/pi-packages.json`。`scripts/install_pi_extensions.py` は、設定に残った `npm:pi-web-access`（pin 付きも）を `pi remove` で排除してから宣言を入れる。
2. Pi 本体の計測は全機体で止める。`scripts/install_pi_extensions.py` が `~/.pi/agent/settings.json`（`PI_CODING_AGENT_DIR` 尊重）に `enableInstallTelemetry: false` と `enableAnalytics: false` を書く。個人の package 宣言など他の設定はそのまま残す。
3. 宣言に `npm:@ollama/pi-web-search` があり、その機体に `ollama` がないとき、`scripts/install_pi_extensions.py` は <https://ollama.com/download> の公式 command で Ollama を入れる。失敗しても WARN で止まらない（extension 配置は続く。refuse された extension が他を止めないのと同じ規則）。

## Consequences

### Positive

- web 検索が 1 つの extension に定まり、tool 名の衝突で Pi の起動が失敗しない。
- pi.dev への匿名 install report が全機体で止まり、設定ファイルを見ればそれが保証される。
- Ollama のない機体でも `just deploy`（単独では `just pi-extensions-install`）の一度で web 検索まで揃う。

### Negative

- web 検索がローカルの Ollama に依存する。Ollama を入れられない（あるいは入れたくない）機体では `web_search` が使えない。
- Ollama の導入・起動は機体の性能と権限に左右される（macOS の install.sh は /Applications への導入と symlink を行い、`ollama serve` の常駐は別途必要）。
- `pi-web-access` が提供していた他の tool（fetch 系など）が同じ名前では使えなくなる。

### Neutral

- 計測を止める key は `pi` 自身ではなく dotfiles の script が書く。`pi` が知らない key は書き換えないことを sandbox で確認済み。
- `~/.npmrc` の 7 日 quarantine には影響しない。Pi の package は `~/.pi/agent/npm/.npmrc`（`min-release-age=0`）側から入るため。

## 備考

ADR-0056 / 0057 は Claude Code の plugin、本 ADR は Pi の package と対象が違うが、「宣言を dotfiles に置き、script が全 home（Pi は home 1 つ）に揃える」と同じ構造を踏襲している。
