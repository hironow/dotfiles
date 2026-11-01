# 計画: Windows と WSL の実機で見つかった doctor の誤った WARN を直す

**Date:** 2026-11-01
**Status:** Approved（2026-11-01 19:32、所有者。D1・D2・D3 とも推奨どおり）。実装済み、Windows と WSL の再確認待ち（§9）
**Branch:** `fix/doctor-windows-wsl-warn`
**Related:** [ADR-0066](../adr/0066-doctor-warns-only-what-needs-action.md)（Proposed、本計画の基準）、[ADR-0065](../adr/0065-kernel-cve-is-evidence-only.md)（Proposed、kernel は WARN 止まり）、[ADR-0062](../adr/0062-one-windows-ollama-for-wsl.md)（Ollama の判定は runbook が正）、前の計画 [doctor-os-aware-warn](doctor-os-aware-warn.md)（§10 で、Windows・WSL・Linux 固有の WARN は各機体の結果を見てから別の計画にするとした）
**Blocking decisions:** なし（D1〜D3 は所有者が裁定済み）
**Graduates to:** [ADR-0066](../adr/0066-doctor-warns-only-what-needs-action.md)（Context と Decision 2・5 に反映）

入力: #526 のコメント（2026-11-01 19:17 JST）。trade 機の native Windows と WSL（Ubuntu 24.04、カーネル `6.18.54.1-microsoft-standard-WSL2`）で、main `f582147` の `just doctor` を実行した結果。

## 1. 目的と完了の条件

ADR-0066 Decision 1 の基準（WARN は「その機体で operator が見るか、手を動かすべきこと」だけ）に、Windows と WSL の実機で外れていた行を合わせる。ERR の判定と exit code の契約は変えない（ADR-0066 Decision 6）。

完了の条件:

- 下の 2.1〜2.7 の各項目に、先に失敗するテストを書いてから実装し、`just ci` が exit 0。
- PR の CI が全 pass。
- この Mac で、merge 後の main で `just ca-doctor-build` → `just kernel-doctor-build` → `just doctor` を実行し、WARN と ERR が今（`warn=1 err=1`）より増えず、exit code が変わらない（1、system python の ERR）。ca-doctor と kernel-doctor は source が変わると古い binary を `WARN ca-build` / `WARN kernel-build` で止めるので（`tools/ca-doctor/main.go:46`、`tools/kernel-doctor/main.go:121`）、作り直さない確認は数えない。`just ci` の go-test は doctor が使う binary を作り直さない。
- Windows と WSL の実機確認は、trade 機の operator に依頼する（この Mac からは測れない）。依頼には merge 後の SHA を書く。結果（その SHA で作り直した binary の `just doctor`）が PR に届き、§7 の期待どおりに行が変わったこと、残すべき WARN / ERR と exit code が残っていることを確かめた時点で完了とする。届くまでは「実装済み・実機確認待ち」として handover の Windows と WSL の節に残す。

## 2. 変更

### 2.1 Windows の curl（Schannel）が証明書を拒否したとき exit 35 になる（報告 1）

事実（上流の curl `lib/vtls/schannel.c`、`lib/strerror.c` を 2026-11-01 に読んだ）:

- Schannel の handshake の失敗のうち、exit 60（`CURLE_PEER_FAILED_VERIFICATION`）になるのは `SEC_E_WRONG_PRINCIPAL` と `SEC_E_UNTRUSTED_ROOT` だけ。それ以外はすべて exit 35（`CURLE_SSL_CONNECT_ERROR`）で、stderr に `schannel: next InitializeSecurityContext failed: <名前> (0x........) - <説明>` を出す。
- `Curl_sspi_strerror` が名前を出す証明書関係の値は、`CRYPT_E_REVOKED`、`CRYPT_E_NO_REVOCATION_CHECK`、`CRYPT_E_REVOCATION_OFFLINE`、`CRYPT_E_NOT_IN_REVOCATION_DATABASE`、`CRYPT_E_NO_REVOCATION_DLL`、`SEC_E_CERT_EXPIRED`、`SEC_E_CERT_UNKNOWN`、`SEC_E_CERT_WRONG_USAGE` など。

変更（`tools/ca-doctor/probe.go` の `CurlOutcome`）:

- exit 35 で、stderr に `schannel:` と、次のいずれかの名前の直後に空白と `(0x` が続く文字列があれば `CertRejected` とする: `CRYPT_E_REVOKED`、`SEC_E_CERT_EXPIRED`、`SEC_E_CERT_WRONG_USAGE`。
- 失効の確認ができなかったことを示す名前（`CRYPT_E_NO_REVOCATION_CHECK`、`CRYPT_E_REVOCATION_OFFLINE` など）と、意味の広い `SEC_E_CERT_UNKNOWN` は `Unknown` のまま（証明書を判定した結果ではないため）。
- stderr の文字列は今までどおり出力しない（判定に使うだけ）。

テスト（Red を先に）: `probe_test.go` に `CurlOutcome` の表を足す。exit 35 + `CRYPT_E_REVOKED` → `CertRejected`、exit 35 + `CRYPT_E_REVOCATION_OFFLINE` → `Unknown`、exit 35 で `schannel:` が無い（OpenSSL の handshake 失敗）→ `Unknown`、exit 60 → 今までどおり `CertRejected`、truncated → `Unknown`。

効果: Windows の `ca-live-emudhra-2026-curl` が `unverified=14/14` の WARN から、全部拒否の INFO（ADR-0066 Decision 3）になる。受け入れたホストがあれば ERR のまま。

### 2.2 Windows で control の接続が時々リセットされる（報告 2、原因は IPv6）

事実: trade 機の Windows から control URL へ 10 回中 3 回 `Connection was reset`（curl と python）。WSL からは 10 回とも成功。テストホスト 14 本はリセットされていない（`certificate-rejected=14 unverified=0`）。原因はまだ確かめていない。

変更（`ProbeClient`）: control URL の結果が `Unknown` のときだけ、同じ client で最大 2 回まで再試行する（合計 3 回）。`Accepted` と `CertRejected` は再試行しない。テストホストは再試行しない（報告ではリセットされておらず、到達できないホストの timeout が 3 倍になるのを避ける）。再試行も global の同時実行数の枠を使う。

理由: control は「この client がそもそも TLS でつなげるか」を確かめるためのもので、1 回のリセットではその答えにならない。3 回とも `Unknown` なら今までどおり WARN。未確認を OK にはしない。

テスト: fake の `TLSProber`（control だけ 1 回目 `Unknown`、2 回目 `Accepted`）で INFO になること、3 回とも `Unknown` なら WARN で、control の試行が 3 回で止まること、`CertRejected` の control は 1 回しか試さないこと。

原因は IPv6 だった（2026-11-01、trade 機。[ca-control-ipv4](ca-control-ipv4.md) §1）。control URL は IPv4 と IPv6 の両方のアドレスを持ち、Windows は IPv6 を先に使う。その IPv6 の接続の約半数がリセットされた（curl `-6` は 30 回中 19 回、`-4` は 0 回）。テストホストは IPv4 のアドレスしか持たない。上の 3 回の再試行だけでは揺れが残ったので（8 回中 4 回で WARN）、[#529](https://github.com/hironow/dotfiles/pull/529) で 2 回目を IPv4 に限った（Bun を除く）。どこでリセットされるかは確かめていない。

### 2.3 版の要素が 2 つ（pip `24.0`）だと「解析できない」になる（報告 3）

事実: `stableVersion`（`tools/ca-doctor/policy.go:177`）は `x.y.z` だけを受け付ける。Ubuntu の system pip は `24.0`。pip が修正版として `26.3` のような 2 要素の版を出すと、修正済みでも WARN になる。

変更: 観測した版（ツールが出した版）に限り、`x.y` を `x.y.0` として比べる。PEP 440 と Go の版の付け方（`1.27` = `1.27.0`）のどちらでも、足りない要素は 0 である。事故ルールの修正床（`incidents/*.json` の `minimum`）は今までどおり 3 要素だけを受け付ける（`incidents.go:78` の検証は変えない）。kernel-doctor は変えない（ADR-0065 Decision 3: 文字列全体が `x.y.z` のときだけ比べる）。

テスト（`VersionEvidenceFor`）: pip `24.0` → WARN `24.0 is outside the reviewed fix branches (26)`、`26.3` → OK、`26.2` → ERR（`26.2.0 < 26.2.2`）、`26` → WARN unparseable、`26.3rc1` → WARN unparseable。修正床の `26.2` は検証で拒否されたまま。

効果: system pip `24.0` の WARN は残る（系列外は ADR-0066 の前計画 §4.3 どおり WARN）が、文言が正しくなる。2 要素の修正版が誤って WARN になることが無くなる。

### 2.4 `brew - missing` を OS で出し分ける（報告 4 の前半）

事実: justfile は「Linux では brew は任意（WSL と mise 管理の機体には Homebrew が無い）」（`justfile` の dump の recipe）、「native Windows には brew が無い」（`update-brew`）としている。`scripts/doctor.sh:30` は OS を見ずに `WARN brew - missing` を出す。

変更（`scripts/doctor.sh`）:

- macOS: 今までどおり（有れば OK、無ければ WARN）。
- Linux（WSL を含む）: 有れば OK、無ければ `INFO brew - not installed (optional on Linux; Brewfile steps are skipped)`。
- native Windows（`MINGW*|MSYS*|CYGWIN*`）: 行を出さない（ADR-0066 Decision 5）。
- `log_info` の helper を `log_err` の次に足す（`info` を数える）。今は INFO を数える helper が無く、子の検査の INFO を各 block で数えている。

テスト: `tests/unit/test_doctor_os_gating.py` に、Darwin / Linux / WSL / MINGW の 4 形と brew の有無で表を足す（`has` と `uname` を shell 関数で偽装）。

### 2.5 Windows の `ca-os-bundle` が常に WARN（報告 4 の後半）

事実: `storeInventory`（`tools/ca-doctor/main.go:250`）は `dpkg-query`、`rpm`、`apk`、（macOS では）`brew` を探す。Windows にはどれも無いので、毎回 `WARN ca-os-bundle - OS CA bundle/revocation update state not established` になる。Windows の信頼ストアと拒否リスト（CTL）は Windows Update が更新するもので、package の版は無い（CA runbook の「native Windows」の行）。

変更:

- [Tidy First の構造の commit] `storeInventory(ctx)` を `storeInventory(ctx, goos string)` にし、呼び出し側は `runtime.GOOS` を渡す（振る舞いは変えない）。
- [振る舞い] `goos == "windows"` のとき `INFO ca-os-bundle - Windows root store and disallowed list are updated by Windows Update, not by a package; not inventoried here; check Windows Update and organisational certificate distribution (docs/runbook/ca-doctor.md)` を返す。Linux で package の版が取れないとき（未知のディストリビューション）は今までどおり WARN。

テスト: `storeInventory(ctx, "windows")` が INFO の 1 行を返し、PATH 上の package コマンドを実行しないこと（PATH を空の dir にする）。既存の dpkg-query の fake のテストは `"linux"` を渡す。

### 2.6 kernel の第三者の数値と助言の行を INFO にする（報告 5、判断 D1）

事実: WSL では CVE 1 件につき、`kernel-version-*`（`unverified-vendor`）1 行、`kernel-observed-*`（NVD などの数値）1 行、`kernel-advice-*`（記録に固定された助言の文）5 行の、計 7 行が WARN になる（`tools/kernel-doctor/main.go:201-207`）。observed と advice は毎回同じ文で、機体ごとの状態を表さない。

変更（推奨）: `kernel-observed-*` と `kernel-advice-*` を INFO にする。`kernel-version-*`（修正床に届かない、またはベンダーのカーネルで未判定）と `kernel-sysctl-*` は今の level のまま。これで WSL の kernel の WARN は CVE 1 件につき 1 行（`kernel-version-*`）になる。

ADR との関係:

- ADR-0065 Decision 4（kernel の所見は WARN 止まりで `err` に入れない）は上限の決まりで、INFO はその下にある。Decision 2（`just doctor` が advisory として表示する）も、INFO は表示されるので満たす。
- ADR-0066 Decision 1 と 2 は kernel-doctor を対象に含み、第三者の数値（事実）と固定の助言（注意書き）は INFO と定めている。PR #526 は macOS でしか確かめず、この 2 種の行を見落とした。本変更は実装を ADR-0066 に合わせるもので、決定を変えない。
- それでも報告者が所有者の判断を求めたので、D1 として確認する。

テスト: kernel-doctor の `assessmentFindings` で observed と advice の level が INFO、version は WARN のまま、`Report` と `--json` の exit code が WARN の version 行だけで決まること。`tests/unit/test_doctor_kernel.py` は INFO を数えることを既に確かめているので、件数の期待値だけ直す。runbook `kernel-doctor.md` に「数値と助言は INFO」を 1 文足す。

### 2.7 Ollama の docker-desktop の未検査を INFO にする（報告の Windows の WARN 一覧から、判断 D2）

事実: `ollama_host.py`（`scripts/ollama_host.py:1531`）は「停止中の distro」と「docker-desktop（プラットフォーム管理）」を同じ `WARN ollama-inspection - ... stopped/platform-managed, uninspected` にまとめている。Ollama の runbook（ADR-0062 Decision 4 が判定の正本とする、`docs/runbook/ollama-windows-wsl.md:159`）は「停止中や接続不能の WSL は … 未検査の WARN とする。プラットフォーム管理の distro も未検査と表示する」と書き、プラットフォーム管理の distro を WARN とは定めていない。docker-desktop は ADR-0062 の Ollama のクライアントになりえない（Docker Desktop の内部の distro）。

変更（推奨）: docker-desktop は `INFO ollama-inspection - WSL docker-desktop: platform-managed, not an Ollama client; not inspected` とする。停止中の利用者の distro は runbook どおり WARN のまま。runbook の 159 行目に「プラットフォーム管理の distro は INFO で表示する」と明記する。

テスト: `tests/unit/test_ollama_host.py` の既存のテスト（1633 行付近、`Ubuntu` 停止 + `docker-desktop`）を、停止中の `Ubuntu` は WARN、`docker-desktop` は INFO、どちらも起動しない、に分ける。

## 3. ADR-0066 の更新（Proposed のうちに直す）

- Context に、2026-11-01 の Windows と WSL の実測（`ok=61 warn=11 err=1 info=20` / `ok=54 warn=12 err=1 info=26`）と、本計画で直した行を足す。
- Decision 5 の例に「Homebrew の行は macOS だけで WARN、Linux では INFO、native Windows では出さない」「Windows の OS の CA ストアの行は INFO」を足す。Decision 2 の例に「kernel の第三者の数値と固定の助言」を足す。
- Consequences の「Windows と WSL の実機での確認が別に要る」を、確認済みの事実と残り（本計画の変更後の再確認）に直す。
- 「決定（記入待ち）」の A 案のアクション（「`feat/doctor-os-aware-warn` の PR を merge し …」）は既に済んでいるので、今の状態に直す。
- 決定変更ログには何も足さない（Proposed のままなので）。decision-queue の行の「次の一手」を直す。
- 起票時の cross-DR の確認をやり直す（ADR-0062、ADR-0065 との関係）。矛盾が出たら止めて所有者に相談する。

## 4. 順序（commit の単位）

1. `refactor(ca-doctor): pass the OS to the CA store inventory`（2.5 の構造の変更だけ）
2. `fix(ca-doctor): count Schannel certificate rejections from curl`（2.1）
3. `fix(ca-doctor): retry an unknown control probe before calling it unknown`（2.2）
4. `fix(ca-doctor): compare two-part tool versions as x.y.0`（2.3）
5. `feat(ca-doctor): report the Windows root store as INFO`（2.5 の振る舞い）
6. `feat(doctor): show brew only where it is used`（2.4）
7. `feat(kernel-doctor): show third-party figures and advice as INFO`（2.6、D1 が承認されたときだけ）
8. `feat(ollama): show the platform-managed distro as INFO`（2.7、D2 が承認されたときだけ）
9. `docs(adr): record the Windows and WSL measurement in ADR-0066`（3）

各 commit は Red → Green の順。commit 後に `git show --name-only` で中身を確かめる。worktree で作業し、`/Users/nino/dotfiles` は main のまま。draft PR → `just ci` → worktree で `just ca-doctor-build` → `just kernel-doctor-build` → `just doctor`（変更の効果を Mac で見る）→ ready → CI 全 pass → squash merge（`--watch`、`--auto` は使わない）→ main で同じ 3 つを実行して §1 の Mac の条件を確かめる → PR に merge 後の SHA と §7 の依頼をコメントする → handover を更新する。

## 5. 所有者の判断

- D1（承認）: kernel の observed と advice の行を INFO にするか（推奨: する。ADR-0066 Decision 1・2 の適用で、ADR-0065 Decision 4 の上限の内側）。
- D2（承認）: Ollama の docker-desktop の行を INFO にするか（推奨: する。runbook の文言どおり。停止中の利用者の distro は WARN のまま）。
- D3（承認）: control の再試行（2.2）を入れるか、原因が分かるまで WARN のままにするか（推奨: 入れる。最大 3 回、control だけ。原因の調査は handover に残す）。

## 6. 範囲外

- trade 機の `ollama-owner`、`ollama-health`、`ERR ollama-bridge`: 本当の構成の問題。operator がその機体で Windows の Ollama を起動し、`ollama_host.py --setup` を実行する（runbook どおり）。
- `python-retired`、`rtk-pi-extension`、Windows の `docker - daemon unreachable`: その機体で手を動かせば消える本物の WARN。
- `kernel-version-*` の `unverified-vendor` の WARN: ADR-0065 Decision 3 どおり（ベンダーのカーネルは判定しない）。
- 停止中の利用者の WSL distro の `ollama-inspection` WARN: Ollama の runbook が WARN と定めている。
- Linux で package の版が取れない場合の `ca-os-bundle` WARN。

## 7. Windows と WSL での再確認の依頼（PR に書く）

trade 機で `git pull`（merge 後の SHA であることを `git rev-parse --short HEAD` で確かめる）→ `just ca-doctor-build` → `just kernel-doctor-build` → `just doctor`。期待: Windows は `ca-live-*-curl` が INFO（control が通れば）、`brew` と `ca-os-bundle` の WARN が消え、docker-desktop の行が INFO。WSL は `brew` が INFO、kernel の WARN が 1 行。結果を PR にコメントする。

## 8. レビューの記録

- Codex 1 回目（2026-11-01）: REVISE、指摘 1 件。
    - [P2] 変更後の binary を作り直した確認と、対象 OS での確認が完了の条件に無い → **採用**。`tools/ca-doctor/main.go:46` と `tools/kernel-doctor/main.go:121` で、source が変わると古い binary が `WARN ca-build` / `WARN kernel-build` で止まることを確かめた。§1 の完了条件、§4 の順序、§7 の依頼に、作り直しと SHA の確認を足した。
- Codex 2 回目（2026-11-01、`resume --last`）: APPROVE、新しい指摘なし。前回の P2 は §1 と §4 で解消と判定。

## 9. 実装の結果（2026-11-01、この Mac）

- `just ci` は exit 0（unit 1995 passed。golangci-lint と `go test` は ca-doctor と kernel-doctor の両方で通った）。
- worktree で binary を作り直して `just doctor`: `ok=52 warn=6 err=1 info=31` で、前の計画の §11 と同じ。WARN 6 件のうち 5 件は worktree から実行したための `claude-plugins`、1 件は system pip 21.2.4（系列外）。ERR は system python の `ca-live` の 1 行。本計画の変更は Windows と WSL で効くもので、この Mac の行は変わらない。
- 実装中に計画から変えた点: 2.4 の brew の行は `case "$(uname -s)" in` でなく `if` で書いた。既存のテスト 3 本（`test_doctor_windows.py`、`test_doctor_npm_rogue.py`、`test_retired_python_tools.py`）が「最初の `case "$(uname -s)" in` が Windows 専用の節」として位置を確かめており、最初の `just ci` でそれを壊したため。
- Windows と WSL の再確認は、merge 後に #526 へ依頼した（2026-11-01 20:09、[コメント](https://github.com/hironow/dotfiles/pull/526#issuecomment-6557133995)、§7）。`ca-live` の行は [#529](https://github.com/hironow/dotfiles/pull/529) の確認で Windows と WSL の両方で INFO になった。`just doctor` 全体の結果はまだ届いていないので、本計画は「実装済み・実機確認待ち」。
