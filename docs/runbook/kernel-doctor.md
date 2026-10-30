# Kernel doctor

`just kernel-doctor` は、Linux カーネルの版を「レビュー済みの出典つき修正床」と
突き合わせ、**証拠と不確かさ**を出す。判定ではない。

**このリポジトリは Linux カーネルを同梱・ビルド・固定しない。** だからこの道具は
カーネルを直さないし、直せない。パッチを当てず、更新せず、インストールしない。
「修正済み」とも「脆弱」とも言わない。

証明書は [ca-doctor](ca-doctor.md)、バイナリ内包物は [brotli-doctor](brotli-doctor.md) を使う。
WSL のホスト側の設定は [windows-host](windows-host.md) と [ollama-windows-wsl](ollama-windows-wsl.md)。

## 実行方法

```bash
just kernel-doctor-build   # 明示ビルドのみ。doctor は自動ビルドしない
just kernel-doctor
just kernel-doctor --json
just kernel-doctor-build-all   # linux/darwin/windows × amd64/arm64
```

別のホストの版を、その OS のコマンドを実行せずに調べる。
`--osrelease` を渡すとローカルの `/proc` と `/etc/os-release` は**読まない**。

```bash
# Windows ホストの WSL カーネルを macOS から調べる
just kernel-doctor --osrelease="$(wsl.exe -d Ubuntu -- uname -r)"
```

終了コードは 0 が警告なし、1 が警告または未判定、2 が引数エラー。
**0 を「安全」の条件にしない。** 未判定の行が無いことを意味するだけである。

## 出力の読み方

版の比較結果は 5 つ。`patch_status` と `backport_state` は**常に `unverified`**。

| 結果 | 意味 |
| --- | --- |
| `below-reviewed-fix-floor` | クリーンな上流リリース形で、レビュー済み branch の修正床より下 |
| `at-or-above-reviewed-fix-floor` | 同じく、修正床以上。**ベンダーの backport や実行中のパッチ状態は依然として未確認** |
| `unverified-vendor` | ベンダー／ディストロのカーネル。数値が上流の patch level ではないので比較しない |
| `unverified-branch` | クリーンな形だが、その branch はレビューしていない |
| `unverified-version` | クリーンな上流の `x.y.z` ではない。比較しない |

行の接頭辞は doctor と同じ `LEVEL name - detail`（`scripts/doctor_lines.py`）。

## なぜベンダーのカーネルを判定しないか

Ubuntu の `6.8.0-45-generic` や Debian の `6.1.0-28-amd64` の第 3 成分は、
**上流の patch level ではない**。ベンダー自身の ABI リビジョンである。
上流の修正床と数値で比べると**両方向に間違える**。数値が古くても修正は
backport されていることがあり、逆もある。

だから比較するのは次の両方を満たすときだけにした。

- 文字列**全体**がクリーンな上流リリース形 `x.y.z` である。
  先頭 3 成分を抜き出して残りを捨てると、`6.6.159+`（Linux が実際に付ける）・
  `6.6.159.2`・`6.6.159garbage` がすべて「6.6.159 以上」に化ける。
- `major.minor` がレビュー済み branch に一致する（または mainline の修正版以上）。

それ以外は `unverified` とし、レビュー済み修正床の一覧を出す。
**未判定を「修正済み」として数えない。** 保守側に倒れるのは意図した設計である。

レビュー済み branch の**あいだ**にある branch（例: 6.13〜6.18）は
`unverified-branch` になる。これは意図した挙動で、修正床の一覧と
その branch 自身の stable tree かベンダーの勧告を読む。

## CVE-2026-98432 について

`ipv4: free inet_opt and ireq_opt after an RCU grace period`。CNA は kernel.org、公開
2026-10-15。導入は 2015 年の commit `079096f103fa`（v4.4 期）。レビュー済みの
上流修正版は 5.10.272 / 5.15.223 / 6.1.190 / 6.6.159 / 6.12.113 / 6.18.56 / 7.2.10、
mainline は 7.3。修正は `inet_sock_destruct()` と `tcp_v4_reqsk_destructor()` の
`kfree()` を `kfree_rcu()` にするもの。

**深刻度には争いがある。** 次の 2 つは同じ脆弱性の別の見積もりである。

| 情報源 | スコア | 攻撃複雑度 |
| --- | --- | --- |
| NVD / Tenable / Rapid7 | 9.8 | `AC:L`（容易） |
| Oracle の自社記録（暫定と明記） | 8.1 | `AC:H`（競合を勝ち抜く必要） |

Red Hat の優先度は critical ではなく **high**（Bugzilla は `NEW`、修正版は未確定）。
EPSS は 0.00388（約 0.4%）、CISA KEV 未収載。
**KEV 未収載は「CISA が実悪用を把握していない」であり、公開 exploit の不在の証明ではない。**

引き金は 2 つ。どちらも到達には条件が要る。

1. 再送 SYN を別 CPU が処理する競合（子ソケットが解放される間に SYNACK を組み立てる）。
   この経路は **IP options を持つソケット**（`ip_options_build()` が `optlen` を読む）を要する。
2. request socket の migration。`net.ipv4.tcp_migrate_req=1`、**または**
   `BPF_SK_REUSEPORT_SELECT_OR_MIGRATE` プログラム。

この道具は 2 の sysctl を 1 つ読むが、**0 でも免責にならない**（BPF の経路がある）。
sysctl は network namespace ごとに保持されるので、読んだ値は**現在の namespace のもの**である。
経路 1 と BPF は外部から内省できないので、**調べていない**。

IPv6 側にも同型の問題がある（`tcp_v6_reqsk_destructor()` の `ipv6_opt`。CALIPSO のときだけ設定される）。
これは**別の patch** で扱われ、本 CVE のレビュー済み修正範囲の外である。

## 面ごとの是正

| 面 | カーネルの供給元 | 是正 |
| --- | --- | --- |
| WSL2 と self-hosted runner | Microsoft | **Windows 側で** `wsl --update` |
| ベンダーのカーネル（Debian / Ubuntu / RHEL / SUSE / Amazon） | ベンダー | ベンダーの勧告とパッケージ更新（`apt` / `dnf`）+ **ホストの再起動** |
| devcontainer / emulator / telemetry のコンテナ | ホスト VM / WSL2 | OrbStack・Docker Desktop・WSL2 のカーネルを更新。**イメージ更新では変わらない** |
| macOS ホスト | Apple | 対象外 |

WSL の手順は次に固定する。**再起動の単位はカーネルであり、プロセスやコンテナの再起動では効かない。**

```bash
# Windows 側（管理者 PowerShell）
wsl --update
wsl --shutdown
# 新しいカーネルで起動したことを確かめる
wsl.exe -d <distro> -- uname -r
```

`wsl --shutdown` は**すべての distro と WSL2 VM を停止する**。self-hosted runner は
その WSL の中で動いているので、**実行中のジョブが無い時**に行う（[ADR 0035](../adr/0035-runner-disk-gc.md)）。

`kernel=` で独自カーネルを指定している WSL は別管理である。`wsl --update` では変わらない。
**「更新コマンドが成功した＝修正済み」ではない。** 新しいカーネルで起動したことを
`uname -r` で確かめる。

## 限界

- 版の比較は「報告された文字列」と「レビュー済みの上流修正床」の比較である。
  ベンダーの backport も、実行中のカーネルのパッチ状態も見えない。
- コンテナの中で実行すると `/proc/sys/kernel/osrelease` は**ホストの**カーネルを返す。
  これは露出の正しい答えだが、ホストとコンテナを区別しない。
- 経路 1（IP options 付きソケット）と BPF による migration は調べていない。
  現在の network namespace 以外は調べていない。
- 知っているのは記録済みの CVE だけである。汎用の脆弱性スキャナではない。
- クロスビルドが通ることは、Windows や WSL の実機で観測できたことの証明ではない。
- レビュー記録には期限がある。過ぎると `policy_freshness=overdue` を出す。
  一次情報を読み直して記録を更新する。

## 一次情報

- upstream 勧告: <https://git.kernel.org/pub/scm/linux/security/vulns.git/plain/cve/published/2026/CVE-2026-98432.mbox>
- CVE レコード: <https://osv.dev/vulnerability/CVE-2026-98432>
- Oracle の評価（8.1 / `AC:H`）: <https://linux.oracle.com/cve/CVE-2026-98432.html>
- Red Hat Bugzilla 2553390: <https://bugzilla.redhat.com/show_bug.cgi?id=2553390>
- Tenable（9.8 / EPSS / KEV）: <https://www.tenable.com/cve/CVE-2026-98432>
- Red Hat の CVE ページ: <https://access.redhat.com/security/cve/CVE-2026-98432>

レビュー日は 2026-10-29、レビュー期限は 2026-11-26。
記録の正本は `tools/kernel-doctor/incidents/` にある。
