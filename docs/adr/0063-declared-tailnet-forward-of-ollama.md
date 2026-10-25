# 0063. 宣言した機体だけ、tailnet の中だけの Tailscale 転送を Ollama の公開と数えない

**Date:** 2026-10-25
**Status:** Accepted
**ID:** ADR-0063
**Title:** 宣言した機体だけ、tailnet の中だけの Tailscale 転送を Ollama の公開と数えない
**Decided-date:** 2026-10-25
**Decision-maker:** Hiroto N.
**Decision-maker-contact:** @hironow
**Author:** Claude Code（owner session）
**Author-contact:** @hironow
**Supersedes:** none
**Superseded-by:** none
**Related:** [ADR-0062](0062-one-windows-ollama-for-wsl.md)、[ADR-0064](0064-mirrored-wsl-uses-the-shared-loopback.md)、[tailnet の ACL](../../tofu/tailnet/acl.hujson)、[runbook](../runbook/ollama-windows-wsl.md)、[計画](../plan/ollama-tailnet-forward-and-mirrored-wsl.md)
**Consultation-trace:** 所有者が 2026-10-25 の本セッションで、ある共存機の 11434 の tailnet 転送を「要る：dotfiles 側で認める」と回答した。計画は独立レビューを 3 回受けた（6 件を反映し、止める点なし）。裁定は公開 PR に代理記録した（本人の明示許可）。

## やさしい説明

ある機体では、Tailscale の機能で Ollama の 11434 を tailnet（自分の機体だけの網）に出している。
dotfiles の検査は、これを「2 つ目の Ollama」かつ「外への公開」と数えて ERR にしていた。
所有者はこの転送が要ると決めた。
そこで、機体ごとに宣言ファイルを置いた時だけ、厳しい条件を満たす転送を公開と数えないようにする。
インターネットへの公開（Funnel）は、どんな時も認めない。

## Context

- `scripts/ollama_host.py --check` は、11434 の待受のうち loopback 以外の物を公開（`ollama-exposure` の ERR）とし、正規の本体以外の待受を 2 つ目の本体（`ollama-owner` の ERR）とする。
- Tailscale の TCP 転送（`tailscale serve --tcp`）を使うと、`tailscaled` の子プロセスがその機体の tailnet のアドレスで 11434 を待ち受け、受けた接続を `localhost:11434` に渡す。
- その結果、正規の本体が動いていても doctor は ERR になる。`backend_owned()` も偽になるので、WSL の setup と CLI の口も止まる。
- tailnet の ACL（[`tofu/tailnet/acl.hujson`](../../tofu/tailnet/acl.hujson)）は、どの機体にも Funnel を許さず、tailnet の中だけの `tailscale serve` を唯一の出し方としている。
- 昇格していないユーザーからは、`tailscaled` の子の実行パスは見えない。親のサービス（`Win32_Service` の `Tailscale`）の pid とパス、プロセスの親と作成時刻、`tailscale ip`、`tailscale serve status --json` は読める。
- Windows の 1 行のコマンドは 32,767 文字までで、`-EncodedCommand` はスクリプトを 2 倍にして base64 で広げる。調べのスクリプトはこの判定で上限を超える。

## Decision

1. 転送を認めるのは、ユーザーの宣言ファイル `%USERPROFILE%\.config\dotfiles\ollama-tailnet-forward`（中身は `11434` の 1 行）がある機体だけとしなければならない（MUST）。宣言の無い機体では、Tailscale のコマンドを 1 回も実行しない。宣言は認可の境界ではなく、消せば元の判定に戻る。
2. 宣言があっても、次をすべて満たす待受だけを転送と認めなければならない（MUST）。1 つでも読めない・調べられない時は認めない。
   - ポートが 11434。
   - 待受のプロセスが、動いている Tailscale サービスそのものか、その直接の子の `tailscaled.exe`。子の時は、親の作成時刻が子より前。確かめた後でサービスの pid を読み直し、変わっていない。
   - サービスの実行ファイルが `%ProgramFiles%\Tailscale\tailscaled.exe` で、そのファイルと親フォルダが reparse point でなく、Authenticode が有効で署名者が Tailscale Inc.。CLI の `tailscale.exe` も同じ検証の後で使う。
   - 待受のアドレスが、`tailscale ip` が返すこの機体のアドレスで、`100.64.0.0/10` か `fd7a:115c:a1e0::/48` に入る。
   - serve の設定のどこにも（foreground のセッションを含む）有効な `AllowFunnel` が無い。
   - 11434 の転送先が `127.0.0.1:11434`、または `[::1]:11434` に待受が無い時の `localhost:11434`。11434 を別の handler（foreground、Tailscale Services、web、Tun）が持たず、ほかの転送や web の proxy が 11434 を指さない。
3. 認めた待受は、2 つ目の本体とも公開とも数えず、`OK ollama-tailnet-forward` を出さなければならない（MUST）。宣言があるのに認めなかった待受は、理由とともに `ERR ollama-tailnet-forward` を出し、公開の ERR も残す。
4. Windows の調べのスクリプトは、標準入力で PowerShell に渡さなければならない（MUST）。コマンド行には、標準入力を UTF-8 で読んで実行する短い決まった起動文だけを置く。

## Options Considered

| 案 | 利点 | コスト・リスク | 所有者の選択 |
| --- | --- | --- | --- |
| 宣言した機体だけ、厳しい条件で認める | 宣言の無い機体の判定は変わらない。Funnel と転送先の取り違えを拒否できる | PowerShell の判定が増える。Tailscale の CLI と JSON の形に頼る | 選択済み |
| 宣言なしで `tailscaled` の待受をいつも認める | 設定が要らない | 宣言していない機体の公開まで黙って通す | 不採用（既定の非公開と両立しない） |
| 認める機体の名前を repo に書く | 機体側の作業が要らない | 公開 repo に機体の情報を載せ、ほかの機体にも広がりうる | 不採用 |
| ERR のまま、転送を外してもらう | 検査が変わらない | 所有者が要ると決めた転送を使えない | 不採用（所有者の回答） |

## Consequences

### Positive

- 宣言した機体で、正規の本体と認めた転送だけがある時、doctor と WSL の setup・CLI の口が使える。
- Funnel、別の転送先、別の handler、pid の再利用、偽のパスは、どれも ERR のまま残る。
- 調べのスクリプトがコマンド行の長さの上限に縛られなくなる。

### Negative

- PowerShell の判定と、Windows でしか走らないテストが増える。Windows の CI のジョブを足した。
- Tailscale の `serve status --json` の形が変わると、認めなくなる（ERR に倒れる）。
- 宣言した機体の doctor は、Tailscale の CLI を最大 3 回（各 5 秒まで）呼ぶ。

### Neutral

- tailnet の ACL と Tailscale の設定は変えない。dotfiles は転送を作りも消しもしない。
- WSL の中の検査（[ADR-0064](0064-mirrored-wsl-uses-the-shared-loopback.md)）は、Windows 側の判定を使う。

## 他の DR との照合

[ADR-0062](0062-one-windows-ollama-for-wsl.md) と同じ走査（全 60 件と、0062・0064）を行った。
Tailscale の公開について決めた有効な記録は無い（0004 は retired の control plane の記録で、[ADR-0045](0045-coder-control-plane-retired.md) が置き換え済み）。
tailnet の ACL（IaC）の Funnel を許さない方針と一致する。
矛盾、重複、誤解、関連の誤り、関係の錯誤は検出していない。

## 決定（2026-10-25）

- **Accepted**。決定者: Hiroto N.（@hironow）。本セッションでの所有者の回答を、公開 PR に代理記録した。
