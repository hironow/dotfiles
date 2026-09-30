# native Windows の機体で動かす

native Windows（WSL の外）で、このリポジトリの recipe、スクリプト、テストを動かすときに踏みやすい罠をまとめる。
justfile の shell 設定、`scripts/*.sh`、mise の設定、Windows で動く Python を変える前に読む。

## just の recipe を動かす shell

Windows は、裸の `bash` を PATH より先に `C:\Windows\System32\bash.exe`（WSL の入口）で解決する。
そのため、bash を使う recipe が WSL に落ちることがある（WSL を入れていない機体では起きない）。
影響は recipe の書き方で 2 通りに分かれる。

- **普通の recipe**（`doctor`、`harden-env`、`deploy`、`clean` など、`bash scripts/*.sh` を呼ぶもの）：justfile の `set windows-shell := ["sh", …]` と前置き処理で解決済みで、PowerShell から直接実行できる。System32 に `sh.exe` はないので `sh` は Git Bash になり、前置き処理が `/usr/bin` を PATH の先頭に足してから内側の `/usr/bin/sh` を起動する。素の msys の `sh` は呼び出し元の PATH の順序をそのまま使うので、この前置きがないと内側の `bash` が WSL に落ちる。前置きは recipe の shell の中だけの変更である（`tests/unit/test_windows_shell_usr_bin_path.py` と `test_deploy_clean_linewise.py` が守る）。
- **shebang の recipe**（`dump`、`scaffold-agent-baseline` など、`#!/usr/bin/env bash` で始まるもの）：`set shell` の影響を受けず、`env` が PATH の順序で `bash` を探す。素の PowerShell では System32 が先なので失敗する。Git Bash から実行する（`/usr/bin` が先頭にあるので Git Bash の `bash` になる）。

Git の `usr\bin` を PATH の先頭に恒久的に足せば PowerShell からも動くが、`find` や `sort` などの Windows 版のコマンドを覆い隠すので勧めない。
PowerShell から shebang の recipe を実行すると、登録済みの PATH に Git の `usr\bin` がなければ `could not find cygpath` で全部失敗する。
`just doctor` の Windows の節が cygpath の不足を検出し、直し方を表示する。

ネイティブのプロセス（Python など）から bash を起動するときも、裸の `bash` ではなく Git Bash の実体を指定する（テストでは `tests/unit/_bash_hook.py` の `resolve_bash()`）。
Claude Code は hook を Git Bash で実行するので、hook のコマンドに `C:\` のパスを書くとバックスラッシュが失われる（`/` 区切りで書く）。

## uv の設定ファイル

native Windows の uv は `~/.config/uv/uv.toml` ではなく `%APPDATA%\uv\uv.toml` を読む。
これがないと供給網の隔離が効かず、`uv run` がコミット済みの `uv.lock` を書き換え、pre-commit の lint で commit が止まる。
`just harden-env` が両方に書き、`just doctor` が不足を検出する。

## mise の npm backend

mise の npm backend のパッケージマネージャーは `bun` にする（ADR 0036）。
既定の `auto` は mise 内蔵の aube を使い、その配置では claude-code の postinstall が動かない。
すると native binary（約 263MB）が展開されず、`bin/claude.exe` が 500 バイトの stub のまま残り、`node claude.exe` の実行で `ERR_UNKNOWN_FILE_EXTENSION` になる。
install は成功として終わり、何も報告しない。
npm-global の野良のコピーが PATH で mise の版を隠していると動き続けて見えるので、その野良を消す `just prune-rogue-npm-globals` が `claude` を壊したように見える。

- backend を変えても、導入済みのものは直らない。`mise uninstall` と `mise install` で入れ直すまで stub のままである。
- bun は shim を `node_modules/.bin` ではなく `<install>/bin/` に置く。mise activate の前に開いたシェルは古い `.bin` を PATH に持ったままなので、シェルを開き直す（`mise env` は正しい `bin/` を返す）。
- Windows では、削除済みの exe でもプロセスは動き続ける。消したあとも今のセッションは動くが、次の起動ではそのパスがない（実体のパスは `ps -W` で確かめる）。
- WinGet の版は、野良のコピーが PATH で勝っているあいだは見えず、野良を消すと現れる。mise の版より古いことがあり、`just doctor` の `winget-shadow` が検出する。

bun backend では `npm_args` は読まれない（ADR 0040。bun は `bun_args` だけを読む）。
claude-code の native binary が動くのは、bun の既定の信頼リストに載っていて postinstall が走るからである。
postinstall が必要で信頼リストにない npm の道具を足すときは、`bun_args` か trustedDependencies を検討する。

## self-hosted runner の PATH

runner のジョブは mise activate を通らないので、Machine の PATH に scoop の shims、`.bun\bin`、mise の shims を入れている（`install_runner_svc_win.ps1` と `restore_machine_path.ps1`）。
mise activate を通らないプロセス（ジョブや IDE）では、PATH で先に来る scoop や bun のコピーが使われ、mise の版と少しずれることがある。
runner のサービスを止めて対話セッションで動かしていても、User の PATH に mise の shims はないので、Machine の PATH の shims は外さない。

## Python のファイルと文字コード

日本語版の Windows では、locale の文字コードが cp932 である。
`Path.read_text()`、`write_text()`、`open()`、subprocess の `text=True` は、`encoding=` を省くと cp932 で読み書きする。
このリポジトリの Python は、テキストの読み書きに必ず `encoding="utf-8"` を渡し、subprocess の出力は `encoding="utf-8", errors="replace"` で読む（`tests/unit/test_text_io_encoding.py` が検査する）。
Claude Code や Pi と stdin と stdout でやり取りするスクリプトは、読む前に `jev_launch.use_utf8_stdio()` を呼ぶ。

bash に渡す `PATH` に `C:\` のパスを `:` でつなぐと、ドライブ名のコロンで分割されて壊れる。
テストでは `tests/unit/_bash_hook.py` の `bash_path()` で `/c/...` の形に直す。
