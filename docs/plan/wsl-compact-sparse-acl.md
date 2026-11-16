# 計画 (改訂 2): `just wsl-compact` の sparse 判定を直し、vhdx の広すぎる ACL を警告する

## なぜ

2026-11-17、WSL の distro を `wsl --manage --move` で D: へ移すと、vhdx の sparse が外れた
(`fsutil sparse queryflag` は「スパースに設定されていません」、属性 `SparseFile` も無し、実占有 = 論理サイズ 227 GB)。
それなのに `just wsl-compact` は `sparse    : yes` と表示した。

- 判定 (`scripts/wsl_compact.sh:58`) は `fsutil sparse queryflag … | grep -qi 'sparse'` で、言語で変わる文言を grep している。
  英語では "This file is set as sparse" と "This file is NOT set as sparse" の両方に一致し、どちらも yes になる。
  この機体 (cp932) では、Git Bash から直接実行すると日本語の文言になり、一致しない (レビュアーの実測)。
  `just` 経由で yes になった理由 (その経路の fsutil が英語を返したのか) は特定していない。どちらにせよ、文言で判定する限り正しくならない。
- sparse と判定したときも diskpart の手順を表示する (`:109-131`)。しかし diskpart と Optimize-VHD は、sparse な vhdx を
  "Virtual hard disk files must be uncompressed and unencrypted and must not be sparse" で拒否する
  (WSL issue #4103、MS Q&A 1526083)。表示どおりに操作すると、`wsl --shutdown` で runner を止めた後に失敗する。
- 同じ移動で、D:\ の既定の ACL (`Authenticated Users:(OI)(CI)(IO)(M)`、`Users:(OI)(CI)(IO)(GR,GE)`) を継承すると、
  vhdx を `CodexSandboxOffline/Online` (Users の一員) から読み書きできることが分かった。
  vhdx は distro 全体で、runner の認証情報を含む。今回は手で絞ったが、気づく仕組みが無い。
- 見つからなかったときの案内 `wsl --manage <distro> --get-location` (`wsl_compact.sh:40`、`wsl_fsck.sh:38`) は、
  WSL 3.0.5 の `wsl --help` に無い。案内の文が 2 か所に複製されていたので、2 か所が同時に壊れた。

## 変えること

1. `scripts/wsl_vhdx_lib.sh`:
    - `wsl_vhdx_path` は、レジストリの `VhdFileName` を読む (無ければ `ext4.vhdx`)。
    - 見つからなかったときの案内を関数 `wsl_vhdx_locate_hint` 1 つにまとめる。
      案内は `reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Lxss" /s` (DistributionName・BasePath・VhdFileName が一緒に出る)。
      `wsl_compact.sh` と `wsl_fsck.sh` の両方から呼ぶ。
    - `wsl_vhdx_facts <windows-path>` は、vhdx の生の事実を PowerShell 1 回で読み、行ごとに出す:
      `sparse 0|1|?`、`user <SID>`、`owner <SID>|?`、`allow <SID> <name>` (Allow の ACE ごと。継承した ACE も含む)、ACL が読めなければ `allow ?`。
        - Get-Acl は使わない。この機体では、Git Bash から呼ぶと pwsh 7 の `PSModulePath` を引き継ぎ、
          `CouldNotAutoloadMatchingModule` で失敗する (実測)。.NET の `[IO.File]::GetAttributes` と `[IO.File]::GetAccessControl` を使い、
          先頭で `$env:PSModulePath=[IO.Path]::Combine($PSHOME,'Modules')` に戻す (`scripts/jev_launch.py:40-51`、`scripts/ollama_host.py:47-49` と同じ)。
        - 属性と ACL は別々に try し、読めなかった項目だけを `?` にする (属性は ACL が読めなくても読める)。
        - path は環境変数で渡し、出力の CR は落とす。
    - `wsl_vhdx_untrusted_sids` は、facts を標準入力で受け、信頼できない SID を出す純粋な関数 (I/O なし)。
      信頼するのは、利用者の SID、`S-1-5-18` (SYSTEM)、`S-1-5-32-544` (Administrators)、接頭辞 `S-1-5-83-` (NT VIRTUAL MACHINE。WSL が付ける)、
      接頭辞 `S-1-15-` (AppContainer の検査にしか効かない)。`S-1-3-4` (OWNER RIGHTS) は所有者として扱う。
      所有者が信頼外なら、それも出す。ACL が読めなければ `?` を出す。`scripts/jev_core.py:383-401` の許可リストと同じ考え方。
2. `scripts/wsl_compact.sh`:
    - `sparse` は yes / no / unknown の 3 通り。fsutil は使わない。
    - sparse のとき: diskpart の手順を出さない。代わりに次を出す。
        - distro の中で消した分は fstrim で自動的に返ること。
        - diskpart と Optimize-VHD は sparse な vhdx を拒否すること (WSL の `--manage --compact` も拒否するという報告があるが、この機体では未検証)。
        - 余りを返すには先に `--set-sparse false` が要り、その間 vhdx が最大で 論理 − 実占有 = N GB まで膨らみうること。N はスクリプトが持っている値で出す。
          膨らむことは第三者の実測 (VRAM Lab) だけが根拠なので、「最大で」と書く。
    - sparse でないとき: 今の diskpart の手順を出す。あわせて、WSL 3.0.1 以降の `wsl --manage <distro> --compact` は、この機体では未検証だと 1 行書く。
    - unknown のとき: 手順は出さず、属性を読めなかったことを書く。
    - 信頼できない SID があれば `WARN` を出す。実際に見つかった SID と名前を並べ、vhdx の親 (BasePath) の継承を切る `icacls` の例を示す
      (`/inheritance:r /grant:r` は WSL が付けた明示的な ACE を残す。ファイルだけを絞ると、次に作られる vhdx で元に戻る)。
    - 冒頭の注釈の「`--allow-unsafe` が要る」(`:16-18`) を、WSL 3.0.5 の help に合わせて直す (`--set-sparse` に `--allow-unsafe` は無い)。
      sparse に切り替えないという方針は変えない (ADR 0035)。
3. `scripts/wsl_fsck.sh`: 案内を `wsl_vhdx_locate_hint` に替える。
4. runbook `docs/runbook/runner-disk-gc.md` §vhdx から C: への返却 を、この PR の変更に合わせて書き直す。
   「WSL の vhdx は通常 sparse」(:103) は「`--move` で sparse が外れることがある (2026-11-17 の実例)」に、
   「`--allow-unsafe` が要る」(:108) は 3.0.5 の help に合わせる。
   「`wsl --manage --move` の後は、`just wsl-compact` で sparse と ACL を確かめる」を足す。

## やらないこと

- sparse の切り替えや compact を自分で実行すること。表示だけで、今までどおり実行しない。
- `wsl --manage --compact` の挙動の検証 (operator の判断で見送り。案内では未検証と明記する)。
- `just doctor` への ACL 検査の組み込み (operator の判断で別 PR)。
- この PR で触らない文書の古い記述 (`config/wsl/wslconfig` と `scripts/wslconfig_conf.sh` の sparseVhd の理由) は、別の文書の PR で直す。

## TDD

- **[Refactor、先に構造の commit]** `tests/unit/test_podman_gc_simulation.py` の `require_bash_fakes` を、偽物の一覧を引数に取る共有の helper にする (`tests/unit/_bash_fakes.py`)。挙動は変えない。
- **[Red]** `tests/unit/test_wsl_compact.py` を新しく作る。
    - BASH_ENV の関数で、`uname`、`reg.exe`、`cygpath`、`stat`、`du`、`wsl.exe`、`powershell.exe` を偽物にする。`fsutil` は呼ばれたら `exit 91` にする。
      PATH は Git の bash と usr/bin だけに絞り、System32 に届かないようにする。
      `run_bash` に `companions=(VHDX_LIB,)` を渡す。偽の `cygpath -u` は cwd からの相対パスを返し、テストがその場所にファイルを作る。実行前に共有 helper で事前確認する。
    - ケース:
        - 旧実装の再現: 偽の fsutil が英語の "This file is NOT set as sparse" を返すとき、旧実装は yes を出す (Red で確認し、新実装では fsutil が呼ばれない)。
        - sparse でなく、余りが大きい: `sparse    : no`、diskpart の手順と `--compact` が未検証であることが出る。
        - sparse で、余りが大きい: `sparse    : yes`、diskpart の手順が出ない。拒否されることと、`--set-sparse false` に要る N GB が出る。
        - 属性が読めない: `sparse    : unknown`、手順が出ない。
        - ACL: この機体の実測の ACE (S-1-5-83-1-…、S-1-15-3-1024-…、544、18、利用者) だけなら WARN を出さない。
          `S-1-5-11`、`S-1-5-32-545`、機体固有の `S-1-5-21-…-1009` を足すと WARN を出し、その SID を並べる。所有者が信頼外でも WARN。
          ACL が読めなければ unknown と出し、安全とは言わない。
        - vhdx が見つからない: `--get-location` を案内せず、`reg query … /s` を案内する (`wsl_fsck.sh` も同じ関数を使うことを静的に確かめる)。
        - `VhdFileName` がレジストリにあれば、その名前のファイルを測る。
    - `wsl_vhdx_untrusted_sids` を、lib を読み込んで直接テストする (純粋な関数)。
    - Windows だけで動く実 PowerShell のテスト: `$env:PSModulePath='C:/nonexistent-powershell7-modules'` にしたうえで `wsl_vhdx_facts` を一時ファイルに実行し、
      `sparse 0` → `fsutil sparse setflag` の後に `sparse 1`、非 ASCII を含むパス、CR が残らないことを確かめる (`tests/unit/test_ollama_host.py:238-265` の型)。
    - 静的な検査: `scripts/*.sh` の中の powershell.exe の呼び出しで `Get-Acl` を使わないこと。
    - `tests/unit/test_runner_gc.py:954-957` の「`fsutil sparse queryflag` という文字列がある」という検査は削除する (文字列の検査が今回の誤判定を通した。振る舞いのテストに任せる)。
- **[Green]** 上の 1〜3 を実装する。
- **[Refactor]** 4 (runbook)。

## 確かめ方

- `uvx pytest tests/unit/test_wsl_compact.py tests/unit/test_runner_gc.py tests/unit/test_podman_gc_simulation.py` (Windows の native)。
- 新しく足したファイルも含めて、`markdownlint-cli2` と `shellcheck` を明示的に実行する (`just ci` は `git ls-files` で対象を選ぶので、未追跡のファイルは見ない)。
- `just ci` の lint と unit tests。
- 実機: `just wsl-compact` が、D: の vhdx について `sparse    : no`、ACL の警告なし、diskpart の手順を表示すること (読むだけ)。
  vhdx の親の ACL を一時的に広げて試すことはしない。
