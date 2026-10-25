# 0064. mirrored の WSL にはブリッジを置かず、共有の loopback で Windows の Ollama を使う

**Date:** 2026-10-25
**Status:** Accepted
**ID:** ADR-0064
**Title:** mirrored の WSL にはブリッジを置かず、共有の loopback で Windows の Ollama を使う
**Decided-date:** 2026-10-25
**Decision-maker:** Hiroto N.
**Decision-maker-contact:** @hironow
**Author:** Claude Code（owner session）
**Author-contact:** @hironow
**Supersedes:** none
**Superseded-by:** none
**Related:** [ADR-0062](0062-one-windows-ollama-for-wsl.md)、[ADR-0063](0063-declared-tailnet-forward-of-ollama.md)、[ADR-0058](0058-pi-web-search-ollama.md)、[runbook](../runbook/ollama-windows-wsl.md)、[計画](../plan/ollama-tailnet-forward-and-mirrored-wsl.md)
**Consultation-trace:** 所有者が 2026-10-25 の本セッションで、説明を受けた後に「B で進める」と回答した。計画は独立レビューを 3 回受けた。裁定は [PR #504 の所有者裁定（明示許可による代理記録）](https://github.com/hironow/dotfiles/pull/504#issuecomment-6400086305) に記録した。

## やさしい説明

WSL には、自分だけの網を持つ形（NAT）と、Windows と網を共有する形（mirrored）がある。
NAT では、WSL から Windows の Ollama に届かないので、dotfiles は WSL の中に「橋」を置いていた。
mirrored では、WSL から Windows の Ollama にそのまま届く。
そこに橋を置くと、Windows の Ollama と同じ番号を取り合ってしまう。
そこで、mirrored では橋を置かず、そのまま使えることを確かめるだけにする。

## Context

- [ADR-0062](0062-one-windows-ollama-for-wsl.md) により、WSL は Windows の本体をクライアントとして使う。PR #502 は NAT を前提に、WSL の `127.0.0.1:11434` と `[::1]:11434` に待ち受けるユーザーの systemd のブリッジを置く。
- mirrored の網（`.wslconfig` の `networkingMode=mirrored`）では、WSL と Windows が loopback を共有する。両方が同じ番号で待ち受けると衝突する。dotfiles は `.wslconfig` を管理しない（ADR-0058 の Context）。
- 2026-10-25 に mirrored の共存機で、ブリッジ無しで WSL の `curl http://127.0.0.1:11434/api/version` が Windows の本体の版を返した。`[::1]:11434` は答えなかった（本体は IPv4 の loopback だけで待ち受ける）。
- WSL は 2.0.4 から `wslinfo --networking-mode` で網の形を答える。
- [ADR-0063](0063-declared-tailnet-forward-of-ollama.md) を入れると、この機体で `backend_owned()` が真になり、今のままの setup は mirrored でもブリッジを作ってしまう。
- Pi の web 検索の extension は `http://localhost:11434` を固定で使う（ADR-0058 の Context）。

## Decision

1. 網の形は、WSL の中で `wslinfo --networking-mode` を読んで決めなければならない（MUST）。`nat` ならブリッジを置く（今までどおり）。`mirrored` ならブリッジを置かない。それ以外か読めない時は、ブリッジを作らずに止まる。
2. mirrored の `--setup` は、CLI の口（`~/.local/bin/ollama`）とヘルパーだけを置き、ブリッジの unit を書いてはならない（MUST NOT）。ブリッジの unit が有効か動いている、ブリッジのプロセスがいる、WSL に 11434 の待受がある、またはそれらを読めない時は、何も変えずに止めなければならない（MUST）。古い unit は消さない。
3. ブリッジの本体（`--serve`）は、網の形が `nat` と確かめた時だけ待ち受けなければならない（MUST）。
4. mirrored の WSL の doctor は、次の順で確かめ、途中で外れたら通信を 1 回もしてはならない（MUST NOT）。(1) 網の形が mirrored と決まった。(2) WSL の待受の調べが成功し、11434 の待受が無い。(3) Windows で `127.0.0.1:11434` を持つのが正規の本体だと確かめた。(4) WSL から `127.0.0.1:11434/api/version` を 1 回聞き、Windows と同じ版なら OK。Windows の doctor が WSL の中で走らせる調べは通信しない。
5. CLI の口は、mirrored でも Windows 側の所有を確かめてから Windows の CLI を呼ぶ（今までどおり）。

## Options Considered

| 案 | 利点 | コスト・リスク | 所有者の選択 |
| --- | --- | --- | --- |
| 網の形を読み、mirrored では橋を置かない | 衝突しない。mirrored の共存機でも WSL の setup が通る | 網の形ごとの分岐と検査が増える | 選択済み（「B で進める」） |
| 守りだけ入れる（mirrored では setup を止めるだけ） | 変更が小さい | WSL 側の doctor が ERR・WARN のまま残る | 不採用 |
| 機体を NAT に戻す | dotfiles は今のまま | その機体のほかの WSL のサービスが mirrored の前提で組まれており、大きな見直しが要る | 不採用 |
| 橋を別の番号に置く | 衝突しない | Pi の web 検索は `localhost:11434` 固定なので届かない | 不採用 |

## Consequences

### Positive

- mirrored の共存機で、WSL の setup と CLI の口、Pi の web 検索が使える。橋の衝突も起きない。
- 古い橋が残っていても、setup は変える前に止まり、`--serve` も待ち受けない。

### Negative

- mirrored では、HTTP で直接 `localhost:11434` に繋ぐ道具（Pi の web 検索など）は、橋の接続ごとの持ち主の確認を通らない。代わりに doctor が上の順で確かめる。これは mirrored の網の性質で、橋を置いても避けられない（衝突する）。
- `wslinfo` が無い古い WSL（2.0.4 より前）では、NAT でも橋が作られなくなる。`wsl --update` で直す。
- `localhost` を先に `::1` で試す道具は、断られてから `127.0.0.1` に落ちる。その動きは道具ごとに確かめる。

### Neutral

- NAT の共存機の動きは変わらない。
- dotfiles は `.wslconfig` を変えない。

## 他の DR との照合

[ADR-0062](0062-one-windows-ollama-for-wsl.md) と同じ走査（全 60 件と、0062・0063）を行った。
WSL の網の形を決めた記録は無い。ADR-0058 の Context の「`.wslconfig` を管理しない」とは一致する。
ADR-0035 と ADR-0039 は WSL の disk と bootstrap の記録で、網の形には触れない。
矛盾、重複、誤解、関連の誤り、関係の錯誤は検出していない。

## 決定（2026-10-25）

- **Accepted**。決定者: Hiroto N.（@hironow）。本セッションでの所有者の回答を、[PR #504 の所有者裁定（明示許可による代理記録）](https://github.com/hironow/dotfiles/pull/504#issuecomment-6400086305)。
