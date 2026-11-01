# 計画: ca-doctor の control の再試行を IPv4 で行い、Windows の `control=unknown` の揺れを止める

**Date:** 2026-11-01
**Status:** done(→[CA runbook](../runbook/ca-doctor.md) の「通信と実行の制限」)。Approved（2026-11-01 21:46、所有者。Windows と WSL の両方で worktree を使うことも承認）。[#529](https://github.com/hironow/dotfiles/pull/529) で merge（main `a3dbd5c7`）。結果は §12
**Branch:** `fix/ca-doctor-control-ipv4`（worktree はホームの下の `dotfiles-ca-control-ipv4`）
**Related:** [Windows と WSL の追補計画](doctor-windows-wsl-warn.md)（§2.2 で control の再試行を入れ、原因の切り分けを残した）、[ADR-0066](../adr/0066-doctor-warns-only-what-needs-action.md)（Proposed、D3 = control の再試行を入れる）、[CA runbook](../runbook/ca-doctor.md) 56-61 行
**Blocking decisions:** なし（D1 は独立レビューの指摘で (b) に決まった。§10）

依頼: operator（2026-11-01 20:54）「直す PR をあなたがつくって出しましょうか」。#527 を trade 機の Windows で確かめたところ、control の再試行を入れても `ca-live` の WARN が実行のたびに出たり消えたりする。

## 1. 問題（trade 機で 2026-11-01 に実測、main `8ad86f8`）

`output/ca-doctor/ca-doctor.exe --summary` を Windows で 8 回実行すると、4 回でどれか 1 つのクライアントの control が 3 回の試行のあとも `unknown` になり、その `ca-live-*` 行が WARN、exit 1 になった（diagnostic-go、curl、node、curl。毎回違うクライアント）。WSL では 0 回。

原因の切り分け（`docs/plan/doctor-windows-wsl-warn.md` §2.2 が残した調査）:

| 測定（Windows、各 30 回） | 失敗 |
| --- | --- |
| curl `-6` → control URL | 19/30（`(35) Recv failure: Connection was reset`） |
| curl `-4` → control URL | 0/30 |
| node `tls.connect` 既定 / `family: 4` | 13/30 / 0/30 |
| python `socket.create_connection` 既定 / `AF_INET` のソケット | 15/30 / 0/30 |
| bun `fetch` 既定 | 0/30 |
| curl 既定 → example.com（baseline） | 0/40 |
| WSL の curl 既定 → control URL | 0/40 |

- control URL `https://emudhra.we-have-a-problem.com/` は GitHub Pages で、A（`185.199.108-111.153`）と AAAA（`2606:50c0:8000-8003::153`）の両方を持つ。Windows の既定の接続先は IPv6（curl の `remote_ip` は `2606:50c0:8001::153`）。
- 14 のテストホストは A だけを持つ（`204.168.130.246`、`54.39.60.141`、AAAA なし）。テストチェーンは今も IPv4 で接続している。
- WSL（NAT）は IPv4 だけで外へ出るので起きない。Defender のネットワーク保護は無効（`EnableNetworkProtection=0`）。どこでリセットされるか（ルーター、ISP、GitHub 側）は確かめていない。
- 今の再試行（`tools/ca-doctor/probe.go` の `controlAttempts = 3`）は待ち時間なしで同じ経路を 3 回試す。1 回あたり約 5 割失敗すると、1 クライアントで 3 回とも失敗する確率は約 1/8、5 クライアントのどれかが落ちる確率は約 5 割で、実測と合う。

つまり今の control は、テストチェーンが通らない経路（IPv6）を測っている。control の問い（「このクライアントは、正しい証明書の TLS につなげるか」）に、この機体の IPv6 経路の不調が混ざって答えられていない。

## 2. 守ること

- 未確認のものを OK や INFO にしない。control が IPv4 でも `unknown` なら今までどおり WARN（ADR-0066 Decision 6、runbook 87 行）。
- ERR の判定と exit code の契約は変えない。テストホストを 1 つでも受け入れたら ERR。
- テストチェーンは 1 回だけ、今の経路で試す（到達できないホストの timeout を増やさない）。
- baseline（`ca-https-*`、example.com）は変えない（失敗していない）。
- 試行の回数（control は最大 3 回）と、全体の期限（30 秒）、同時接続の枠（12）は変えない。

## 3. 変更

### 3.1 control の 2 回目を IPv4 で試す

`ProbeClient` の control の試行を、そのクライアントが同じ接続方法のまま IPv4 に限れる場合は次の順にする（最大 3 回は変えない）。

1. 1 回目: 今と同じ（クライアントの既定の接続先の選び方）。`Accepted` か `CertRejected` なら、それで終わり。
2. 2 回目: `unknown` のときだけ、IPv4 に限って試す。
3. 3 回目: まだ `unknown` なら、既定の選び方でもう一度試す。

IPv4 に限れないクライアント（bun）は、今と同じく既定の選び方で最大 3 回試す。

理由: テストホストは IPv4 しか持たないので、IPv4 の経路で control が通れば、それはテストチェーンと同じ経路で「このクライアントは正しい証明書の TLS につなげる」ことの答えになる。1 回目と 3 回目を既定のまま残すので、今 control が通る機体（Mac、WSL、Linux）の結果は変わらず、IPv6 だけの網（NAT64）で 1 回目が一時的に失敗したときの回復の機会も残る。3 回とも `unknown` なら WARN のまま。

### 3.2 各クライアントの IPv4 の試し方

`TLSProber` の interface は変えない。IPv4 に限ることは prober の値の属性（`GoProbe.IPv4`、`ExternalProbe.IPv4`）にし、`ProbeClient` は既定の prober と、IPv4 の prober（限れないクライアントは `nil`）の 2 つを受け取る。どのクライアントに IPv4 の prober を渡すかは、`main.go` の live client の組み立てを関数に切り出して 1 か所で決める。

| クライアント | 既定（変えない） | IPv4 |
| --- | --- | --- |
| diagnostic-go | `http.Transport` の既定の dial | 同じ Transport で `DialContext` を `net.Dialer` の `"tcp4"` にする |
| curl | 今の引数 | 今の引数に `--ipv4` を足す（プロキシの設定の扱いは既定と同じ） |
| node | `nodeProbe`（`tls.connect`） | 同じスクリプトに引数 `4` を渡し、`family: 4` を付ける |
| python | `pythonProbe`（`socket.create_connection`） | 同じスクリプトに引数 `4` を渡し、`AF_INET` のソケットで接続する |
| bun | `bunProbe`（`fetch`） | なし（`nil`）。既定で 3 回 |

bun を外す理由: Bun 1.4.4 の `fetch` は `family` を無視する（A しか持たない github.com へ `family: 6` でも status 200）。Bun の `node:tls` は `family` に従うが、`fetch` と違ってプロキシの設定を使わない直接接続で、テストチェーン（`fetch`）とは接続の条件が違う。その成功で control を通すと、`fetch` 側の未確認を別の接続方法で埋めることになる（§2 に反する）。bun の `fetch` は trade 機の Windows で 0/30 失敗だった。万一 `ExternalProbe{Kind: "bun", IPv4: true}` が作られても、コマンドを実行せず `unknown` を返す。

### 3.3 文書

- `docs/runbook/ca-doctor.md` 58-61 行: 再試行の説明を「2 回目は IPv4 だけで試し、3 回目は既定に戻る。テストホストは IPv4 しか持たず、Windows では control（GitHub Pages）への IPv6 の接続が約 5 割リセットされた（2026-11-01、trade 機）。Bun の fetch は接続先の IP の種類を指定できないので、既定で 3 回試す」に直す。
- ADR-0066 は変えない。D3（control の再試行を入れる）の決定は同じで、どの経路で試すかは runbook に書く実装の詳細。
- `docs/handover.md`（ローカル）の Windows の節: 原因が分かったことと、この PR の結果を書く。

## 4. テスト（Red を先に書く）

- `probe_test.go`: 既定と IPv4 で別々の `scriptedProber` を渡し、`TestProbeClientRepeatsAnUnknownControl` を次に直す（テストチェーンは全部 `CertRejected`）。
    - 既定 `unknown` → IPv4 `Accepted`: INFO。既定 1 回、IPv4 1 回。
    - 既定 `unknown` → IPv4 `unknown` → 既定 `Accepted`: INFO。既定 2 回、IPv4 1 回（IPv6 だけの網の回復）。
    - 既定 `unknown` → IPv4 `unknown` → 既定 `unknown`: WARN。既定 2 回、IPv4 1 回。
    - 既定 `Accepted`: INFO。IPv4 0 回。
    - 既定 `CertRejected`: WARN。IPv4 0 回。
    - IPv4 の prober が `nil`（bun）: 既定 `unknown` が 3 回で WARN、既定 3 回。既定 `unknown` → `Accepted` で INFO（今の振る舞いのまま）。
- `TestProbeClientDoesNotRepeatTestChains`: テストチェーンは既定で 1 回だけ、IPv4 は 0 回。
- live client の組み立て（切り出した関数）: diagnostic-go、curl、node、python は IPv4 の prober を持ち、bun は `nil`。`ExternalProbe{Kind: "bun", IPv4: true}` はコマンドを実行せず `unknown`。bun の control が既定で 3 回とも `unknown` なら、テストチェーンが全部 `CertRejected` でも WARN（直接接続の成功で埋めない）。
- 外部コマンドの引数（偽の `Commands` で記録する）: curl の IPv4 だけに `--ipv4` が入る。node と python の IPv4 だけに末尾の `4` が入る。既定の引数は今と同じ（構造の変更で振る舞いが変わらないことを固定する）。
- 本物のクライアント（`TestExternalProbeAdaptersAgainstLocalTLS`、入っていなければ skip）: curl、node、python の `IPv4: true` の probe で、127.0.0.1 の TLS サーバに `Accepted`、`https://127.0.0.1:1/` に `unknown`。Schannel だけの curl は今と同じく skip。
- diagnostic-go: `GoProbe{IPv4: true}` で 127.0.0.1 のサーバに `CertRejected`。IPv6 のループバックで待つ TLS サーバ（`[::1]`、使えなければ skip）に対し、`GoProbe{}` は `CertRejected`、`GoProbe{IPv4: true}` は `unknown`（IPv4 に限られていることの証明）。

## 5. 順序（commit の単位）

1. `docs(plan): plan the IPv4 retry for the CA control probe`（本計画）
2. `refactor(ca-doctor): build the live client list in one function`（構造だけ。`main.go` の live client の組み立てを関数に切り出す。振る舞いは変えない。既定の引数と client の並びを固定するテストを先に足す）
3. `fix(ca-doctor): retry an unknown control over IPv4`（3.1、3.2、3.3 の runbook。Red → Green）

各 commit の後に `git show --name-only` で中身を確かめる。

## 6. 作業の場所と流れ

- この機体の `%USERPROFILE%\dotfiles` は main から動かさない（runner の GC / autostart の実行元）。`git worktree add ..\dotfiles-ca-control-ipv4 -b fix/ca-doctor-control-ipv4 origin/main` で作業し、終わったら `git worktree remove` する。
- この機体には署名鍵がないので、ブランチの commit は署名なしになる。ruleset（`protect`）は main の削除と強制 push を禁じるだけで、署名は求めていない。main の commit は GitHub の squash merge が署名する。
- draft PR → `go test -race` と golangci-lint（ca-doctor）と `just ci` → ready → CI 全 pass を `gh pr checks --watch` で確かめる。merge は所有者が決める。

## 7. 完了の条件

- 4 のテストが先に失敗し、実装で通る。`go test -race ./...`（tools/ca-doctor）、golangci-lint、`just ci` が通る。native Windows で `just ci` の一部が動かない場合は、動かなかった leg と理由を PR に書き、CI の結果で補う。
- trade 機の Windows で、worktree で作った binary の `ca-doctor --summary` を 10 回実行し、`control=unknown` が 0 回（変更前は 8 回中 4 回）。各回の `ca-live-*` の level を PR に貼る。
- trade 機の WSL で、同じ SHA を Linux 側でビルドして確かめる（Windows の `.exe` を WSL から起動すると Windows のプロセスとして動き、Linux 側の検査にならない）。WSL の `~/dotfiles` も main から動かさず、`git worktree add` で別の worktree を作り、zsh のログインシェルで `just ca-doctor-build` → `just ca-doctor --summary` を 1 回実行する。条件: `OK ca-build`、`INFO ca-platform - WSL Linux; ...`、各 `ca-tool-*` が Linux 側の実行ファイル、`ca-live-*` が変更前と同じ（5 クライアントとも INFO）。
- PR の CI がすべて成功。

## 8. 失敗したときの戻し方

squash merge 1 つなので `git revert <merge commit>`。ローカルの binary は `just ca-doctor-build` で作り直す。worktree はブランチごと消せる。

## 9. 範囲外

- どこで IPv6 の接続がリセットされるかの調査（この機体の網の問題。handover に残す）。
- baseline（example.com）の経路（失敗していない）。
- テストチェーンの接続の仕方（A しか持たないので今も IPv4）。

## 10. 所有者の判断

- **D1. bun の IPv4 の試行。** → **(b) bun は既定の `fetch` で 3 回のまま**（独立レビュー P1 で決まった。§3.2）。不採用: (a) Bun の `node:tls` で IPv4 を試す（直接接続の成功で `fetch` の control を埋めることになる）。

## 11. 独立レビューの記録

1 回目（Codex、2026-11-01、判定 REVISE、指摘 3 件）。3 件とも確かめて採用した。

| # | 指摘 | 確かめたこと | 対応 |
| --- | --- | --- | --- |
| P1 | bun の `node:tls`（直接接続）の成功を、`fetch`（プロキシの設定を使う）の control の成功として数えると、`fetch` の未確認を別の経路で埋める | runbook 56 行「curl と Bun はプロキシ設定の影響を受け得る」、`tools/ca-doctor/policy.go:45`（control が `Accepted` でチェーンが全部拒否なら INFO） | bun を IPv4 の対象から外した（§3.2、D1 = (b)）。`TLSProber` に `ProbeIPv4` を足すのをやめ、IPv4 の prober を `nil` にできる形にした。bun の回帰テストを足した（§4） |
| P2 | 2 回目と 3 回目を IPv4 に固定すると、IPv6 だけの網で 1 回目が一時的に失敗したとき、今ある既定の経路での回復がなくなる | `probe.go` の今の再試行は 3 回とも既定 | 順を「既定 → IPv4 → 既定」にした（§3.1）。回復のテストを足した（§4） |
| P2 | Windows の `.exe` を WSL から起動しても Windows のプロセスとして動くので、WSL の確認にならない | `tools/ca-doctor/main.go` は `runtime.GOOS` で検査を分ける | WSL では同じ SHA を Linux 側でビルドする手順と、確かめる行を §7 に書いた |

2 回目（Codex、`resume --last`、判定 APPROVE、新しい指摘なし）。前回の 3 件はすべて計画上解消と判定された。

## 12. 実装の結果（2026-11-01、[#529](https://github.com/hironow/dotfiles/pull/529)）

- trade 機の Windows で、変更後の binary の `ca-doctor --summary` を 10 回実行し、`control=unknown` は 0 回（変更前は 8 回中 4 回）。
- trade 機の WSL で、同じ SHA を Linux 側でビルドした: `ca-build` は OK、`ca-platform` は WSL Linux、`ca-tool-*` は Linux のパス。main（`8ad86f8`）と変更後の binary を 5 回ずつ交互に実行し、10 回とも 5 クライアントの `ca-live` が INFO で `control=accepted`。
- `go test`（Windows と WSL）、`go test -race`（WSL）、golangci-lint、markdownlint は通った。native Windows の `just ci` は、golangci-lint が `emulator/bigtable-cli` を処理している途中で機体のメモリが足りなくなり止めた（その前の ruff、ty、pytest は通った）。PR の CI は全 pass。
- この Mac で、PR のブランチの `go test -race`（156 件）、golangci-lint、Windows と Linux へのクロスビルドが通った。`ca-doctor --summary` を 3 回実行し、5 クライアントの `ca-live` は毎回 INFO。WARN と ERR の行は main と同じ（system python の 2 行）。
- 範囲外で見たこと: 変更後の binary の 24 回中 2 回（Windows 18 回中 1、WSL 6 回中 1）、curl のテストチェーン 1 本が unknown（`unverified=1/14`）になり WARN になった。control は 2 回とも通っていた。Windows で curl を 42 回続けて試しても再現しなかった。原因は未確認。本計画はテストチェーンの経路を変えていない。
