# Windows 共存機の Ollama：宣言した tailnet 転送を認め、mirrored の WSL にはブリッジを置かない

**Date:** 2026-10-25
**Status:** 実装中。独立レビュー 1 回目の 6 件（Funnel の確認範囲、`localhost` の転送先、PID の再利用、接続前の所有確認の順序、稼働中のブリッジ、配線の証明）を反映し、2 回目と 3 回目は止める点なし。A と B は所有者が決めた（2026-10-25）。決定は [ADR-0062](../adr/0062-one-windows-ollama-for-wsl.md)・[ADR-0063](../adr/0063-declared-tailnet-forward-of-ollama.md)・[ADR-0064](../adr/0064-mirrored-wsl-uses-the-shared-loopback.md)。
**Scope:** `scripts/ollama_host.py`、`tests/unit/test_ollama_host.py`、`docs/runbook/ollama-windows-wsl.md`、ADR 1 本と `docs/decision-queue.md` の 1 行。Tailscale の設定、`.wslconfig`、Ollama の起動口は変えない。

## 所有者の依頼と現状

Windows と WSL が同居する機体（以下、共存機）で、所有者は 2026-10-25 に次を決めた。

- Tailscale の TCP 転送で 11434 を tailnet に出している。tailnet の中だけで、Funnel は使っていない。
- この転送は今も要る。dotfiles の検査は、これを違反として扱わない。

その共存機で確かめた事実（2026-10-25、昇格していないユーザー）は次のとおり。

- Windows の 11434 の待受は 3 つある。Scoop の `ollama-full` の `ollama.exe` が `127.0.0.1`。`tailscaled` の子プロセスが、その機体の tailnet の IPv4（`100.64.0.0/10` の中）と IPv6（`fd7a:115c:a1e0::/48` の中）。`[::1]:11434` には何も待ち受けていない。
- `tailscaled` の子プロセスの実行パスは見えないが、`ParentProcessId` と `CreationDate` は読める。親は Tailscale サービス（`Win32_Service` の `Name='Tailscale'`、`State=Running`）のプロセスで、子より 1 秒前に作られた。サービスの `PathName` は `%ProgramFiles%\Tailscale\tailscaled.exe` で、そのファイルの Authenticode は `Valid`、署名者は `O=Tailscale Inc.` である。
- `tailscale serve status --json` の上位の鍵は `TCP` と `Web` だけ（`AllowFunnel` と `Foreground` は無い）。`TCP."11434"` は `{"TCPForward":"localhost:11434"}` である。`tailscale ip -4` と `-6` は昇格なしで読める。
- `just doctor` の `ollama-owner` と `ollama-exposure` は ERR になる。同じスナップショットから `tailscaled` の待受を除いて判定し直すと、どちらも OK になる。原因はこの待受だけである。
- PowerShell の調べ（`WINDOWS_PROBE`）も同じ待受で `$owned` が偽になり、版を聞かない。そのため `ollama-health` が WARN になる。
- `backend_owned()` が偽なので、WSL の `--setup` はブリッジを作らずに止まる。WSL の CLI の口（`client_command`）も止まる。
- WSL の `wslinfo --networking-mode` は `mirrored` である。WSL から `curl http://127.0.0.1:11434/api/version` を打つと、ブリッジ無しで Windows の Ollama が答える（`0.40.5`）。`[::1]:11434` は答えない。WSL に 11434 の待受もブリッジの unit も無い。
- mirrored では、Windows と WSL が同じ番号で待ち受けると衝突する。この機体で過去に起きた。今の WSL の設計は、WSL の中の `127.0.0.1:11434` と `[::1]:11434` にブリッジを置く。runbook も「NAT を維持する」と書いている。dotfiles は `.wslconfig` を管理していない。

## 方式

### A. 宣言した機体だけ、tailnet の中だけの Tailscale 転送を認める（所有者の決定）

- **宣言**：機体ごとの宣言ファイルを repo の外に置く。`%USERPROFILE%\.config\dotfiles\ollama-tailnet-forward`（中身は `11434` の 1 行だけ）。無い、または中身が違う機体の判定は今と同じ。宣言はユーザー単位の設定の選択であって、本人に対する認可の境界ではない。消せば元の判定に戻る。どちらも runbook に書く。
- **転送と認める条件**（すべて満たすときだけ。1 つでも読めない・調べられないなら認めない）：
  1. 待受のポートが 11434。
  2. **プロセスの系譜**：Tailscale サービスが `State=Running` で `ProcessId` が 0 でない。待受のプロセスが、そのサービスのプロセスそのものか、`ParentProcessId` がサービスの PID で名前が `tailscaled` の子である。子のときは、親の `CreationDate` が子の `CreationDate` 以前である（PID の再利用で、無関係な親を親と取り違えないため）。調べ終わった後にサービスの PID をもう一度読み、変わっていない。
  3. **実体**：サービスの `PathName`（引用符を外したもの）が `%ProgramFiles%\Tailscale\tailscaled.exe` と一致する。そのファイルと親フォルダが reparse point でない。Authenticode が `Valid` で、署名者に `O=Tailscale Inc.` を含む（wslrelay の例外と同じ検証）。
  4. **アドレス**：待受のアドレスが、`tailscale ip -4` と `tailscale ip -6` が返すこの機体の tailnet のアドレスのどれかと一致し、`100.64.0.0/10` か `fd7a:115c:a1e0::/48` に入る。CLI は `%ProgramFiles%\Tailscale\tailscale.exe` を、3 と同じ検証をしてから使う。
  5. **Funnel は一切認めない**：`tailscale serve status --json` の全体（`Foreground` の下のセッションごとの設定も含む）に、真の `AllowFunnel` が 1 つでもあれば認めない。
  6. **転送先は正規の backend だけ**：`TCP."11434".TCPForward` が `127.0.0.1:11434` なら認める。`localhost:11434` なら、`[::1]:11434` に待受が無い時だけ認める（`localhost` は IPv6 にも解決されうる。そこに wslrelay などが居れば、転送は確かめた backend と別の所へ行く）。それ以外の先は認めない。11434 以外の TCP 転送と `Web` の proxy の先に、11434 を指すものがあれば認めない（宣言していない別の出し方になるため）。
- **認めた待受の扱い**：PowerShell の `$backendListeners` と Python の `_backend_listeners()` から外す（第 2 の backend と数えない）。`ollama-exposure` の判定からも外す。代わりに `OK ollama-tailnet-forward` の行を出し、転送が在ることを毎回見せる。認めた転送だけが残る時に限って、PowerShell は版を聞く（`ollama-health`）。
- 認めない待受（条件のどれかが外れる、宣言が無い）は、今と同じく ERR。wslrelay の例外とほかの判定は変えない。
- **作り**：判定は PowerShell の関数 `Test-DotfilesTailnetForward` に、入力（待受の行、サービスとプロセスの情報、署名、`tailscale ip` の結果、serve の JSON、宣言の中身、`[::1]:11434` の待受）を引数で渡す形にする。集める部分（`Get-CimInstance`・`Get-NetTCPConnection`・`Get-Item`・`Get-AuthenticodeSignature`・CLI の呼出し・版の問合せ）は、テストで差し替えられる小さな関数に分ける。

### B. WSL が mirrored なら、ブリッジを置かず、共有の loopback で Windows に届くことを確かめる（所有者が承認、2026-10-25）

- **網の形の判定**：WSL の中で `wslinfo --networking-mode` を読む。`nat` なら今と同じ。`mirrored` なら下の扱い。それ以外、または読めないなら「不明」とし、`--setup` はブリッジを作らずに止め、doctor は WARN にする。
- **接続の前に確かめる順序**（mirrored の doctor・setup・`--inspect-local` のどの経路でも同じ）：
  1. 網の形が `mirrored` と確定した。
  2. WSL の待受の調べ（`ss`）が成功し、WSL の中に 11434 の待受が無い。`ss` が失敗したら「待受なし」とみなさず、そこで止める。
  3. Windows 側の所有の確認（`backend_owned()`）が成功した。`--inspect-local`（Windows の doctor が WSL の中で走らせる調べ）は、Windows 側の判定を知らないので、HTTP を打たない。WSL の loopback の確認は WSL の doctor だけで行う。
  4. ここまで通った時だけ、WSL から `http://127.0.0.1:11434/api/version` を 1 回打つ。版が Windows の答えた版と同じなら OK。
  どこかで外れたら、HTTP は 0 回で止まる。
- **mirrored の `--setup`**：CLI の口（`~/.local/bin/ollama`）は今と同じく置く。ブリッジの unit は書かず、有効にもしない。変える前に、dotfiles のブリッジの unit が有効（enabled）か、動いている（active・activating）か、`--serve` のプロセスが居るか、WSL に 11434 の待受があるかを読み、1 つでも在れば何も変えずに例外で止まり、止め方（`systemctl --user disable --now ollama-windows-bridge.service`）を案内する。状態が読めない時も成功にしない。
- **`--serve` 自体**：網の形が `nat` と確かめられた時だけ待ち受ける。`mirrored` と不明では、待ち受けずに終了する（古い unit が手で起こされても衝突しない）。
- **mirrored の doctor**：`ollama-bridge` の代わりに `ollama-loopback` を出す。WSL に 11434 の待受があれば ERR、Windows の正規の backend が止まっていれば WARN、版が違えば ERR、上の順序をすべて通って版が同じなら OK。`OLLAMA_HOST` の判定（`conflicting_config`）は今と同じ。
- WSL の CLI の口は、今と同じく Windows 側の所有を確かめてから Windows の CLI を呼ぶ。mirrored でも変えない。
- **A と B の結びつき**：A が入ると共存機で `backend_owned()` が真になり、今の WSL の `--setup` は mirrored でもブリッジを作れるようになる。そのため、B の全体を見送る場合でも、「mirrored と不明では `--setup` がブリッジを作らず、`--serve` が待ち受けない」守りだけは A と同じ PR に入れる。B が merge されるまで、mirrored の機体で WSL の `just deploy` を回さない。

### 文書と決定の記録

- ADR を 3 本足す。DR 間整合検査で、ADR-0058 の Decision 3・4（共存機の Ollama は WSL 側に 1 台）と PR #502 の実装（Windows 側に 1 台）の矛盾を検出し、所有者が「別の ADR で置き換える」と裁定した（2026-10-25）。0062 が #502 の設計を記録して 0058 の該当部分を置き換え、0063 が A、0064 が B。`docs/decision-queue.md` の決定済みログに 3 行足し、0058 は Status 行だけを直す。裁定は公開 PR に代理記録する。
- runbook に、宣言のしかたと消し方、宣言が認可の境界でないこと、何を確かめるか（Funnel は決して認めない、転送先の条件）、mirrored の扱いを書く。「NAT を維持する」は「NAT ならブリッジ、mirrored なら共有の loopback」に直す。
- 別のコミットで、runbook に「単独インストーラ版のアンインストーラは既定パスのモデルを消す」警告を足す（共存機で 2026-10-25 に実際に消えた）。

## TDD の順（小さな振る舞いごとに Red → Green → 検証）

1. **Python の芯（Linux と Windows の CI）**：`windows_findings()`・`_backend_listeners()`・`backend_owned()` に、分類済みの `tailnet_forward: true` の待受を渡すと、`ollama-owner` と `ollama-exposure` が OK、`ollama-tailnet-forward` が OK。`tailnet_forward` が無い・偽なら今と同じ ERR。
2. **PowerShell の判定関数（Windows の CI）**：wslrelay の例外のテストと同じ形（関数の差し替えと `-EncodedCommand`）。全部揃う時だけ真。次はどれも偽：宣言が無い・中身が違う、ポート違い、サービスが止まっている・PID が 0、親がサービスでない、名前違い、親が子より新しい、調べの途中でサービスの PID が変わった、パス違い、reparse（ファイル・親）、署名無し・別の署名者・署名の取得失敗、アドレスがこの機体の tailnet のものでない（`0.0.0.0`・LAN・別の `100.x`・範囲外）、`AllowFunnel` が在る（443 経由・`Foreground` の下を含む）、`TCPForward` が別の先（`localhost:8080`・`0.0.0.0:11434`）、`localhost:11434` で `[::1]:11434` に wslrelay が居る、`Web` の proxy が 11434 を指す、CLI の失敗、壊れた JSON。
3. **PowerShell の調べ全体（Windows の CI）**：集める関数をすべて差し替えて `WINDOWS_PROBE` を通しで走らせ、出力の JSON で、認めた待受が `tailnet_forward: true` で backend から外れること、認めない時は今と同じであること、版の問合せが「正規の backend と認めた転送だけ」の時に 1 回、それ以外で 0 回であることを確かめる。
4. **WSL の順序（Linux の CI）**：網の形・`ss`・Windows の所有・HTTP を差し替え、不明・`ss` の失敗・WSL の待受あり・Windows の所有の失敗のどれでも HTTP が 0 回、全部通った時だけ 1 回。`wsl_findings()` の OK・WARN・ERR の各行。`--inspect-local` は mirrored で HTTP を打たない。`nat` は今のテストがそのまま通る。
5. **setup と `--serve`（Linux の CI）**：mirrored で CLI の口を置き、変更系の `systemctl`（`daemon-reload`・`enable`・`restart`）を呼ばない。unit が enabled・active・activating、`--serve` が居る、待受がある、状態が読めない、のどれでも何も変えずに例外。`--serve` は `nat` と確かめた時だけ bind する。
6. **実機（共存機。確かめるコミットを固定する）**：
   - 宣言の前：`just doctor` が今と同じ ERR。
   - 宣言の後、Windows の backend が上がっている間：`ollama-owner`・`ollama-exposure`・`ollama-tailnet-forward`・`ollama-health` が OK。この機体自身から tailnet のアドレスの 11434 に繋ぐと版が返る（転送の経路が backend に届く）。LAN のアドレスの 11434 には繋がらない。backend を止めると、tailnet のアドレスへの接続も失敗する。
   - WSL：main を pull して `just deploy` → CLI の口だけ置かれ、ブリッジの unit が無い → WSL の doctor の `ollama-loopback` が OK、`ollama list`（CLI の口）が動く → Pi の web 検索（`http://localhost:11434` 固定）が WSL から届く（`localhost` が先に `::1` を試して断られた後、`127.0.0.1` に落ちること）→ Windows の backend を止めて上げ直しても衝突しない。
   - 既存のブリッジからの移行は、この機体には元のブリッジが無いので単体テスト（5）で扱う。Funnel は実機で公開せず、実際の設定の形に沿った fixture（2）で扱う。別の tailnet 端末からの到達は、所有者の端末で確かめてもらう（任意）。

## 範囲外

- Tailscale の設定、`.wslconfig`、Windows の Ollama の起動口（トレイアプリや機体固有の起動口）を変えること。
- CA の診断で見つかった Python の件。

## 完了の定義

A（と承認されれば B）の単体テストが Linux と Windows の CI で緑、`just ci` が緑、上の実機の確認がすべて通り、PR が merge され、所有者に結果を返している。
dotfiles のコミットには機体の禁止語の一覧（`~/.config/dotfiles/forbidden-tokens`）が要る。共存機に一覧が置かれるまで、コミットは待つ。
