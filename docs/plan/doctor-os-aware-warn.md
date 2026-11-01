# 計画: `just doctor` の WARN を「その機体で operator が見るべきこと」に絞り、OS ごとに出し分ける

**Date:** 2026-11-01
**Status:** Approved（2026-11-01 17:07、所有者。D1 = 全部拒否は INFO、D2 = ADR を起票）。実装済み（§11）
**Branch:** `feat/doctor-os-aware-warn`
**Related:** [ADR-0065](../adr/0065-kernel-cve-is-evidence-only.md)（Proposed、kernel は WARN 止まり）、[CA runbook](../runbook/ca-doctor.md)、[kernel runbook](../runbook/kernel-doctor.md)、[kernel の計画](kernel-cve-evidence.md)（D3）
**Blocking decisions:** なし（D1・D2 は所有者が裁定済み）
**Graduates to:** [ADR-0066](../adr/0066-doctor-warns-only-what-needs-action.md)（Proposed → 所有者の裁定で Accepted）

依頼: operator（2026-11-01）「doctor の処理もその OS に基づいたもので、WARN を過剰に出しすぎないようにしたい」

## 1. 問題（この Mac で 2026-11-01 に実測）

`just doctor` は `ok=55 warn=103 err=15`。WARN 103 件の内訳は次のとおりで、operator が手を動かすべきものはほぼ無い。

| 件数 | 行 | 中身 | 性質 |
| --- | --- | --- | --- |
| 70 | `WARN ca-chain-emudhra-2026-{bun,curl,diagnostic-go,node,python}` | 14 のテストホストすべてで `certificate-rejected`（正しく拒否） | 同じ事実の 1 ホスト 1 行の展開 |
| 5 | `WARN ca-live-emudhra-2026-<client>` | `accepted=0 certificate-rejected=14`、「CA-specific distrust unverified」 | 上の 14 行の要約 |
| 10 | `WARN ca-tool-<tool>` | 「active executable: <path>; ... is not TLS remediation proof」 | 環境の事実と注意書き |
| 4 | `WARN ca-env` | `SSL_CERT_FILE` / `CURL_CA_BUNDLE` / `REQUESTS_CA_BUNDLE` / `PIP_CERT` が設定済み | runbook（`ca-doctor.md:123`）が macOS で勧める設定そのもの。各ファイルは `OK ca-file-*` で検査済み |
| 4 | `WARN ca-version-emudhra-2026-{certifi,pip}-{python,system-python}` | 「unsupported/unparseable release」 | 3 件は誤分類: uv の venv には certifi も pip も無く、system python には certifi が無い（未導入を「解析できない版」と言っている）。残る 1 件は system python の pip 21.2.4（レビュー済みの修正版がある系列は 26 だけ） |
| 7 | `ca-platform` `ca-remediation` `ca-coverage` `ca-advice-*`×2 `ca-rust` `ca-os-bundle` | 検査の範囲と限界の注意書き | 毎回同じ文。対処は無い |
| 1 | `WARN ca-git-verify` | 「no explicit http.sslVerify」 | Git の既定（検証する）が上書きされていないだけ |
| 1 | `WARN kernel-coverage` | カーネル検査の限界の注意書き | darwin では `OK kernel-not-applicable` と同時に出ており、検査していないものの注意書きになっている |

ERR 15 件も、`/usr/bin/python3` がテストホストを受け入れたという 1 つの事実を、14 ホスト分と要約 1 行に展開したもの。

OS に合わない行もある（WARN ではないが OK を水増しする）: macOS で `OK PATH-windows`（WSL の `/mnt` 漏れの検査）、`OK ollama-policy - ... not applicable on this host`。

## 2. 守ること（変えない原則）

- 未確認のものを OK にしない（`ca-doctor.md:87`、ADR-0065 Decision 3）。
- ERR の意味と doctor の終了コードは変えない。テストホストを 1 つでも受け入れたクライアントは ERR、ERR があれば exit 1。
- 証拠の全量は残す。1 ホスト 1 行の詳細は `just ca-doctor`（単体実行）でこれまでどおり出す。
- kernel の所見は WARN 止まり（ADR-0065 Decision 4）。

## 3. 新しい決まり

**WARN は「この機体で operator が見る、または手を動かすべきこと」だけに使う。** 検査の範囲の注意書きと環境の事実は、新しい level `INFO` で出す。`INFO` は表示するが、OK にも WARN にも数えず、終了コードに影響しない。doctor の最終行は `Doctor summary: ok=N warn=N err=N info=N` になる。

その OS で意味の無い検査は、行そのものを出さない。

## 4. 変更内容

### 4.1 行の protocol に `INFO` を足す

- `scripts/doctor_lines.py`: `parse` / `fmt` が `INFO` を扱う。`failed()` は INFO を失敗に数えない。
- `scripts/doctor.sh`: ca-doctor / kernel-doctor / ai_tools_check / ollama_host の各読み取りループが `INFO` 行を受け付け、`info` を数える。ca と kernel の整合性判定（exit code と行の組み合わせ）は、INFO を「OK でも WARN でもない」として扱う。例: ca-doctor が exit 0 で OK と INFO だけを出すのは有効。
- `tools/ca-doctor` と `tools/kernel-doctor` の `Report`: INFO は exit code を上げない（0 = WARN も ERR も無い、1 = WARN あり、2 = ERR あり、は維持）。

### 4.2 ca-doctor に `--summary` を足し、doctor はそれを使う

- `--summary` では `ca-chain-*` の 1 ホスト 1 行を出さない。かわりに `ca-live-<incident>-<client>` の 1 行に件数を載せ、受け入れたホストがあればその名前を並べる。
- 受け入れたホストが 1 つでもあれば、その 1 行は ERR（今と同じ判定）。この Mac では ERR が 15 行から 1 行になり、exit 1 は変わらない。
- `just ca-doctor`（`--summary` なし）は今と同じ全行を出す。
- **古い binary の扱い。** 今の binary は、知らない引数を受け取ると鮮度検査の前に `ERR ca-arguments` と exit 2 を返す（`tools/ca-doctor/main.go:41-42`）。そのままだと doctor.sh はこれを正当な ERR として受け入れ、「作り直せ」という案内が出ない。そこで doctor.sh は、出力が `ERR  ca-arguments` の 1 行だけで exit 2 のとき、結果を受け入れず `WARN ca-build - CA check binary does not support this checkout -- run: just ca-doctor-build; then just doctor` を出す。ほかの ERR は今どおり受け入れる。`--summary` を知っている新しい binary が、古い checkout に対して実行された場合は、今と同じく鮮度検査が `WARN ca-build` を返す。

### 4.3 ca-doctor の行の level を見直す（単体実行と `--summary` の両方）

| 行 | 今 | 変更後 | 理由 |
| --- | --- | --- | --- |
| `ca-tool-*` active executable | WARN | INFO | どの実行ファイルを調べたかという事実 |
| `ca-tool-*` not on PATH（導入は不要と自分で言っている） | WARN | INFO | 対処が無い |
| `ca-tool-*` wrapper / version command failed | WARN | WARN（変えない） | 調べられなかった。operator が見るべき |
| `ca-env` の CA ファイル系（`SSL_CERT_FILE` `SSL_CERT_DIR` `CURL_CA_BUNDLE` `REQUESTS_CA_BUNDLE` `PIP_CERT` `GIT_SSL_CAINFO` `GIT_SSL_CAPATH` `NODE_EXTRA_CA_CERTS`） | WARN | INFO | 中身は `ca-file-*` / `ca-path-*` が検査する。runbook が勧める設定 |
| `ca-env` の proxy 系、`NODE_OPTIONS`、`GODEBUG`、`PYTHONHTTPSVERIFY` | WARN | WARN（変えない） | TLS の挙動を変えうる |
| `ca-env` の ERR 条件 | ERR | ERR（変えない） | |
| `ca-platform` `ca-remediation` `ca-coverage` `ca-advice-*` `ca-rust` | WARN | INFO | 毎回同じ注意書き |
| `ca-os-bundle`（パッケージの版を取れたとき） | WARN | INFO | 版の事実。取れなかったときは WARN のまま |
| `ca-git-verify`（上書きなし） | WARN | INFO「not overridden in this config context (Git default: verify)」 | Git の既定の状態という事実。OK にはしない |
| `ca-version-*-{certifi,pip}`（その Python に入っていない） | WARN「unparseable」 | INFO「not installed in this Python」 | 誤分類の修正 |
| `ca-version-*`（入っているが、レビュー済みの修正版がある系列ではない） | WARN「unparseable」 | WARN「no reviewed fix floor for release branch N」 | 文言だけ正す |
| `ca-live-*`（control が受け入れ、テストホストは全部拒否） | WARN | **operator の裁定（下記 D1）** | |

### 4.4 kernel-doctor を OS で出し分ける

- Linux カーネルを調べなかった機体（darwin、native Windows）では `kernel-coverage` を出さない。`OK kernel-not-applicable` の 1 行だけにする（この行は「この機体から使う WSL や Linux VM は調べていない」と既に書いている）。
- カーネルを調べた機体（Linux、WSL）では `kernel-coverage` を INFO にする。カーネルの所見そのものは WARN のまま（ADR-0065 Decision 4）。

### 4.5 OS に合わない doctor.sh の行を出さない

- `PATH-windows` は WSL でだけ出す（`uname -r` に `microsoft` を含むとき。既存の `wsl-clipboard` 判定と同じ条件）。
- `ollama-policy - ... not applicable on this host` は出さない。対象かどうかの判定は今の `host_policy()`（`scripts/ollama_host.py:337-351`）に任せる。これは native Windows と WSL を対象にし、WSL のカーネル上のコンテナは対象外にする。doctor.sh は OS を自分で判定しない。
- 「対象外」を親に伝える契約: `ollama_host.py --check` は、`host_policy()` が `None` のとき、何も出力せず **exit 3** で終わる（今の exit 0 / 1 / 2 の意味は変えない。実装の前に、3 がまだ使われていないことを確かめる）。doctor.sh は「exit 3 で、取得した出力全体（stdout と stderr）が空」のときだけ黙って次へ進む。exit 3 なのに何か出力がある場合は不整合とみなし、`WARN ollama-inspection` を出して、その出力の OK / INFO / WARN / ERR は 1 つも数えない。そのため、今の「1 行読むたびに数える」ループ（`scripts/doctor.sh:456-466`）を、ca と kernel の読み取りと同じく「先に全行を分類し、exit code との組み合わせを確かめてから数える」形に変える。行が 0 件でほかの exit code（0 / 1 を含む）、または exit 2 以上で 3 以外のときは、今どおり `WARN ollama-inspection - checker unavailable` を出す。
- テストは、macOS、普通の Linux、WSL、WSL のカーネル上のコンテナ、native Windows、checker の実行失敗（行 0 件で exit 1）を分けて書く。

## 5. operator の裁定（2026-11-01 17:07 に裁定済み）

- **D1. テストホストを全部拒否したクライアントの level。** → **(a) INFO**（「CA distrust is not proven」と文に残し、OK にはしない）。不採用: (b) WARN のまま（この Mac で 5 件残る）。
- **D2. 記録の形。** → **ADR-0066 を Proposed で起票**。 この決まり（WARN は対処が要るものだけ、注意書きは INFO）は確立した型の変更なので、新しい ADR を Proposed で起票し、`docs/decision-queue.md` に行を足す（decision-record-governance skill の手順）。ADR-0065 は Proposed なので、kernel-coverage の扱いは新しい ADR から参照し、ADR-0065 の本文は変えない。

## 6. 進め方（TDD、1 PR、commit は structural と behavioral を分ける）

1. worktree を `origin/main` から作る（`git worktree add ../dotfiles-doctor-os-aware -b feat/doctor-os-aware-warn origin/main`）。`/Users/nino/dotfiles` は main のまま。
2. ADR を Proposed で起票し、decision-queue に行を足す（docs commit）。
3. Red → Green を項目ごとに回す。
   - Go: `tools/ca-doctor/*_test.go` に、4.2 と 4.3 の各行の level と文言、`--summary` の集約（全拒否、一部受け入れ、unknown 混在）、`Report` の exit code（INFO だけなら 0）を足す。`tools/kernel-doctor/main_test.go` に、darwin と windows で `kernel-coverage` を出さないこと、linux で INFO になることを足す。
   - Python: `tests/unit/test_doctor_lines.py` に INFO の parse / fmt / failed。`tests/unit/test_doctor_ca.py` と `test_doctor_kernel.py` に、偽の binary が INFO を出したときの doctor.sh の集計と整合性判定（exit 0 で OK+INFO は有効、INFO だけで OK 0 件は無効）。
   - 古い binary の再現: 今の偽 binary は引数を見ない（`tests/unit/test_doctor_ca.py:33`）。今の CLI と同じく、知らない引数に `ERR  ca-arguments` と exit 2 を返す偽 binary を足し、doctor.sh が `WARN ca-build` を出して ERR を数えないことを確かめる。あわせて、本物のセキュリティの ERR（例: `ERR  ca-live-...`）は今どおり数えることも確かめる。
   - ollama: 4.5 に書いた 6 つの場合（`tests/unit/test_ollama_host.py` の既存のコンテナのテストを壊さない）。doctor.sh 側は、偽の checker で「exit 3 で出力なし（黙る）」「exit 3 で OK 行あり（WARN、数えない）」「exit 3 で認識できない文字列（WARN、数えない）」「exit 1 で出力なし（WARN）」を確かめる。PATH-windows: WSL でだけ出ること。
4. runbook（`ca-doctor.md` の「結果と限界」の表と 86-87 行、`kernel-doctor.md`）と README の doctor の説明を同じ commit で直す。
5. ローカルで `just ca-doctor-build`、`just kernel-doctor-build`、`just ci`、`just doctor` を Mac で実行する。
6. PR を draft で作る → ready にする（draft では CI が動かない。`.github/workflows/unit-test.yaml:16,27`）→ CI がすべて成功したのを `gh pr checks --watch` で確かめる → squash merge。

## 7. 完了の条件

- この Mac の `just doctor`: ERR は 1 行（system python の `ca-live`）で exit 1 のまま。WARN は 3 件以下（D1 が (a) の場合）。`ca-chain-*` 行と `kernel-coverage` が出ない。
- `just ca-doctor`（単体）は今と同じホスト別の行を出す（変わるのは 4.3 の level と文言だけ）。
- `just ci` と PR の CI がすべて成功。
- native Windows と WSL の実機で `just ca-doctor-build`、`just kernel-doctor-build`、`just doctor` を operator が実行し、ERR と WARN の行を PR に貼る（クロスビルドの成功は実機の確認ではない）。これは merge 後の handover の Next Actions にも書く。

## 8. 失敗したときの戻し方

- 1 PR の squash merge なので、`git revert <merge commit>` で戻る。ローカルの binary は `just ca-doctor-build` と `just kernel-doctor-build` で作り直す。
- doctor.sh は binary の出力が古い protocol（INFO なし）でも、今と同じに読める（INFO を足すだけで、既存の 3 level の扱いは変えない）。

## 9. 独立レビューの記録

1 回目（Codex、2026-11-01、判定 REVISE、指摘 3 件）。3 件ともコードで確かめて採用した。

| # | 指摘 | 確かめたこと | 対応 |
| --- | --- | --- | --- |
| P1 | 古い binary は `--summary` に `ERR ca-arguments`（exit 2）を返し、doctor.sh がそれを正当な ERR として受け入れる | `tools/ca-doctor/main.go:41-42` で引数の解析が鮮度検査より前。doctor.sh の受け入れ条件は `scripts/doctor.sh:379-381` | 4.2 に古い binary の扱いを足し、6 にそのテストを足した |
| P2 | ollama の対象外を OS だけで決めると、WSL のカーネル上のコンテナの除外と食い違う。行 0 件のチェックを外すと実行失敗も見逃す | `scripts/ollama_host.py:343-351`、doctor.sh の `ollama_lines -eq 0` 判定 | 4.5 を、`host_policy()` に判定を任せ exit 3 で「対象外」を伝える契約に変えた |
| P2 | draft PR では CI が動かないので、「CI を通してから ready」は成り立たない | `.github/workflows/unit-test.yaml:16,27` | 6 の順番を直した |

2 回目（Codex、`resume --last`、判定 REVISE、指摘 1 件）。前回の P1 と 3 件目は「計画上解消」、ollama は「一部対応」とされた。

| # | 指摘 | 確かめたこと | 対応 |
| --- | --- | --- | --- |
| P2 | exit 3 に結果の行が付いたとき、不整合を検出できない。今のループは exit code を確かめる前に OK を数え、認識できない行は数えない | `scripts/doctor.sh:456-466` で、行を読むたびに `ok` などを加算している | 4.5 を「exit 3 かつ出力全体が空のときだけ対象外」にし、ループを分類してから数える形に変えた。6 にテスト 4 件を足した |

2 回目の指摘は、レビュー役が示した修正をそのまま採用した狭い変更なので、3 回目のレビューはしていない。

## 10. 範囲外

- system python の CA の ERR を WARN に落とすこと（runbook の決まりどおり ERR のまま）。
- podman machine の VM のカーネルを kernel-doctor で調べること。
- Windows / WSL / Linux 固有の WARN の洗い出し（この Mac からは測れない。各機体で doctor を回した結果を見てから別の計画にする）。

## 11. 実装の結果（2026-11-01、この Mac）

- `just doctor`（worktree で binary を作り直して実行）: `ok=52 warn=6 err=1 info=31`（変更前 `ok=55 warn=103 err=15`）。WARN 6 件のうち 5 件は、worktree から実行したために `claude-plugins` が marketplace の登録先（`/Users/nino/dotfiles`）と食い違ったもので、本変更とは関係ない。残る 1 件は system python の pip 21.2.4（`outside the reviewed fix branches (26)`）。ERR は system python の `ca-live` の 1 行で、exit 1 は変わらない。
- `ca-chain-*`、`kernel-coverage`、`PATH-windows`、`ollama-policy` の行は doctor に出ない。`just ca-doctor`（単体）はホストごとの 84 行（6 クライアント × 14）を今までどおり出す。
- 実装中に見つけて計画から変えた点: 4.5 の「出力全体が空」は、checker の stdout だけを見るようにした（`2>/dev/null`）。実測で、`uv run` 自身が stderr に出す警告（`VIRTUAL_ENV=... does not match the project environment path`）が `2>&1` で混ざり、exit 3 なのに出力があると判定された。ollama の検査の stderr は以前から数えず、表示もしていなかったので、落としても失うものはない。テスト `test_uv_noise_on_stderr_does_not_break_the_silent_exit` で固定した。
