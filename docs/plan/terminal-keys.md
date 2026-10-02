# 端末キー: tmux 越しの Ctrl+Enter と、単語移動キーの揃え

**Date:** 2026-10-02
**Status:** Proposed（独立レビュー #1・#2 の指摘を検証して反映済み。#3 待ち）
**Branch:** `feat/terminal-keys`（未作成）
**Related:** PR #452（Ctrl+Enter の初版。本件はその tmux 対応） / ADR 0022・0024・0031・0033（`$PROFILE` の managed block。本件では使わない）
**Blocking decisions:** なし（利用者への確認は回答済み: Windows は Ctrl+←/→ を足す / macOS の tmux は 3.2a 以上）
**Graduates to:** 安定後 `done(→ USAGE.md)`。新しい decision は無いので ADR は作らない

## 目的

PR #452 は Ghostty の keybind と `.zshrc` の zle widget で Ctrl+Enter を改行にしたが、
**tmux の中では効かない**（tmux の `extended-keys` は既定 off で、拡張キーを要求しない
アプリには拡張キーを渡さないため、ペイン内の zsh は Ctrl+Enter を区別できる形では受け取れ
ない。落ち方はバージョン依存で、3.4 は何も届かず、3.7c は素の CR = Enter に落ちる =
F4-実測 / F4-実測-2）。あわせて **単語移動（←/→ の 1 単語版）が端末ごとにばらつく**。

本変更は次の 2 点を揃える。

1. Ctrl+Enter = 改行（tmux の中でも）。**対象端末は Ghostty と iTerm2**（端末側から
   拡張キーを送れる端末）。Terminal.app は拡張キーを送る設定を持たないため対象外
   （F14）。tmux の中でも効かせるには、端末 → tmux → アプリの 3 者すべてで拡張キーが
   通る必要がある。
2. 単語移動 = 1 単語左/右。macOS は Option+←/→、Windows と WSL は Ctrl+←/→。
   単語区切りは zsh 既定のまま。**止まる位置の細部は各実装の既定に従う**（右方向で
   zsh と PSReadLine の着地点が違う。F8）。

## 確定させた事実（一次情報で確認済み）

**F1. zsh の既定 emacs キーマップは修飾キー付き矢印を束縛していない。**
zsh 5.9 の `Src/Zle/zle_keymap.c` の `default_bindings()` は `add_cursor_key()` 経由で
**bare なカーソルキーだけ** を追加する（terminfo 由来の 3 文字列を扱い、`buf[3]` が
空でない候補を弾く）。`Src/Zle/zle_bindings.c` の `metabind[]` には `M-b` =
`z_backwardword` / `M-f` = `z_forwardword` がある。
→ `^[[1;3D`（Option+←, xterm 形式）も `^[[1;5D`（Ctrl+←）も現状は zle が解釈できず、
そのまま echo される。

**F2. `xterm-keys` は tmux 2.4 以降 既定 on。** tmux CHANGES:
`* The xterm-keys option now defaults to on.` → 巷の `setw -g xterm-keys on` は no-op。
足すと誤解を招くだけなので足さない。

**F3. `extended-keys always` は tmux 3.2a で追加された（既定は off）。** CHANGES 3.2a:
`* Add an "always" value for the "extended-keys" option; if set then tmux will
forward extended keys to applications even if they do not request them.`
利用者の macOS は 3.2a 以上（回答済み。Homebrew の現行は 3.5a）。

**F4. tmux 3.5 の man 記述では `always` はペインへの出力モードを mode 1 に固定する。**
`When set to always, the client requests are ignored, and mode 1 output is forced.` /
`With respect to parent terminals, when set to on or always, the escape sequence to
enable extended keys is sent, if tmux knows that it is supported.`（マージ済み PR #4038）
→ zsh は拡張キーを要求しないので、この man（3.5 以降）に従えば `on` では client 要求が無く
Ctrl+Enter は素の CR のまま = Enter と同じ。**`always` が必要**。（3.4 では明示 `on` でも
届いた = F4-実測。バージョン依存の挙動には依拠しない。）
（同 PR のリリース告知コメントには「on/always では既定で mode 2 を要求する」とあるが、
これは *親端末への要求* の話。ペインへの出力モードは上記 man の記述を採る。Windows
ホストには tmux が無いので静的検査のみで、実測は下の F4-実測 / F4-実測-2 に置く。）

**F4-実測（2026-10-02、WSL の tmux 3.4、PTY を端末役にして 2 ラウンド再現）**: 配布 conf
（`always` + `xterm*:extkeys`）では `ESC [13;5u`（Ghostty の送る CSI-u）がそのまま届き、
mode-1 の `ESC [27;5;13~` も CSI-u に正規化されて届く（F5 の予想どおり 3.4 は CSI u 側）。
**`extended-keys` の行が無い既定 off ではペインに何も届かない**（CR ではない。未割当の
シーケンス `ESC [199~` はそのまま届くので、拡張キーとして認識した上で捨てている）。`on` を
代入した場合や、明示的に `off` を代入した場合はこの環境では届いた（未代入の既定 off と代入後の
`off` で挙動が違う = 3.4 固有の可能性が高い。3.7c の既定は CR だったので同じ差は出ないと
見られるが、3.7c の明示 `off` は未測）。副作用なし: 素の Enter は `0d`、`ESC [1;5D`
（Ctrl+←）と `ESC b`（Option+←）は無変化。ソース側の裏付けは `tty.c`（`ENEKS` は option が
非 0 のときだけ送る）と `input.c`（`extended-keys == 2` のときアプリの mode 要求を無視する）、
および 3.5a の `options-table.c`（`extended-keys` の既定は `off`、`extended-keys-format` の
選択肢は `csi-u`/`xterm` で既定は `xterm` = `default_num = 1`）。
macOS 3.7c の実機確認は下の F4-実測-2。

**F4-実測-2（2026-10-02、macOS の tmux 3.7c、利用者のレビュー実測。#460 と同じ隔離ソケット +
PTY 方式で 2 ラウンド再現）**: 配布 conf では CSI-u 入力 `ESC [13;5u` も mode-1 入力
`ESC [27;5;13~` もペインには `ESC [27;5;13~` で届く。入力形をそのまま返すのではなく
**mode 1 出力に固定** であり、F4 の man 記述（`always` は client 要求を無視して mode 1 出力を
強制）と整合する（「親端末へは mode 2 を要求する」という読みはこの測定では観測していない。
根拠は CHANGES / man）。
`always` のみ（features 行なし）でも同じ。
**既定（`extended-keys` の行なし）では `0d`（bare CR）= Enter と区別できない**。3.4 の
「何も届かない」と食い違う境界は CHANGES 3.5 の "Revamp extended keys support to more closely
match xterm and support mode 2 as well as mode 1. This is a substantial change to key handling
which changes tmux to always request mode 2 from parent terminal, changes to an unambiguous
internal representation of keys"（3.5 で key 処理が総入れ替え。3.4 は認識して捨てる）。
**境界の候補は 3.5** だが、根拠は CHANGES の記述であって厳密な境界の実測ではない
（実測は 3.4 と 3.7c のみ、3.5/3.5a/3.6 は未測）。対照の `ESC [199~` は両バージョンで素通り（= 「パースできない
ので落ちる」ではない）。副作用なし: 素の Enter `0d`、`ESC [1;5D`、`ESC b` は無変化。
利用者の実機（3.7c）では確認できたが、「3.5 以降すべて」とは言えない。Ghostty の物理キーに
よる end-to-end だけが未実施（手順は末尾のチェックリスト）。

**F5. `extended-keys-format` の既定は `xterm`、その形式では C-S-a は `^[[27;6;65~`。**
man: `For example, C-S-a will be reported as '^[[27;6;65~' when set to xterm, and as
'^[[65;6u' when set to csi-u.`（modifiers = 1 + (1 shift / 2 alt / 4 ctrl)）
→ 既定のままで Ctrl+Enter は `^[[27;5;13~`。これは **PR #452 が既に `.zshrc` に
束縛済み**。`extended-keys-format` は触らない（tmux 3.3/3.4 系が CSI u を出す場合も
`^[[13;5u` として同じファイルが受けている）。

**F6. mode 1 は「標準表現を持たない修飾キーだけ」を拡張形式にする。**
→ `ESC b` / `ESC f`（= M-b / M-f）や `ESC [1;5D`（Ctrl+←）は legacy バイト列のまま
ペインに渡る。Ghostty 側で Option+←/→ を `esc:b` / `esc:f` に固定しても、Ctrl+←/→ を
そのまま通しても、tmux は再エンコードしない。

**F7. Ghostty の keybind action `esc:` は ESC 付きシーケンスを送出する。**
公式 docs は `text:` より `esc:` / `csi:` を推奨し、例として `esc:d`（= 右の単語を
削除 = M-d）を挙げる。modifier は `opt` = `alt` の別名。
（ghostty.org/docs/config/keybind と Option Reference）

**F8. PSReadLine 2.3.6（このホスト）で実行確認した。**
既定束縛は `Ctrl+LeftArrow`→`BackwardWord`（"Move the cursor to the beginning of the
current or previous word"）、`Ctrl+RightArrow`→`NextWord`（"Move the cursor forward to
the start of the next word"）、`Ctrl+Backspace`/`Ctrl+w`→`BackwardKillWord`、
`Alt+d`→`KillWord`。**Alt+矢印は未束縛**（`Get-PSReadLineKeyHandler` で確認）。
`Set-PSReadLineKeyHandler -Chord 'Alt+LeftArrow' -Function BackwardWord` は成功するが、
ファイルには永続化しない（`%APPDATA%\PSReadLine` は作られない）。

**着地点の差（決定）**: zsh の `forward-word` は単語末へ（emacs の `M-f` と同じ）、
PSReadLine の `NextWord` は次単語の先頭へ。**Windows の既定は変えない** — 動いている
既定を配布物で上書きせず、利用者の指の記憶も壊さない。差は本文書に明記する。厳密に
揃えたくなったら `$PROFILE` の managed block に
`Set-PSReadLineKeyHandler -Chord 'Ctrl+RightArrow' -Function ForwardWord` を 1 行足せば
よい（deploy.sh / clean.sh / doctor.sh / tests の既存の型が使える。F13）。今はやらない。

**F9. Windows Terminal は既定で Alt+←/→ をペイン移動に使い、アプリに渡さない。**
microsoft/terminal の生成物 `defaults.json`（`src/cascadia/TerminalSettingsModel/`）:
`{ "keys": "alt+left", "id": "Terminal.MoveFocusLeft" }` / `alt+right` →
`Terminal.MoveFocusRight`（`alt+up/down` も、`alt+shift+arrows` は ResizePane）。
このホストの `settings.json` は `actions: []` と `keybindings` 3 件（ctrl+c / ctrl+v /
alt+shift+d）だけで **上書きしていない** → Alt+矢印は WT が消費する。
**WT は Ctrl+←/→ を束縛していない** → そのままアプリに届く（WT の Actions 一覧の
moveFocus / resizePane に Ctrl+矢印は無い）。

**F10. macOS 標準 Terminal.app は Option+←/→ の単語移動に設定が要らない。**
Apple 公式のショートカット一覧（"Edit a command line"）は
`Move the insertion point forward one word | Option-Right Arrow` /
`backward one word | Option-Left Arrow` を挙げ、**「Use Option as Meta key」の注記が
付かない**（注記が付くのは `Option-D` = 単語末まで削除の行）。→ Option 全体を Meta 化
する副作用（Option+文字 の合成入力が変わる）を案内する必要はない。

**F11. WSL は追加作業が不要。** `uname -s` = Linux で deploy.sh の Unix 分岐に入り、
`~/.zshrc` / `~/.tmux.conf` を同じ symlink で張る（利用者は WSL のシェルを zsh と回答済み）。
tmux は `dump/macbook/Brewfile` が入れる（macOS）。Linux/WSL では利用者が入れた版に従う。

**F12. tmux の config エラーは致命的ではない。** tmux(1):
`tmux shows any error messages from commands in configuration files in the first
session created, and continues to process the rest of the configuration file.`
→ 3.2a 未満の tmux では `extended-keys` の行が警告 1 行になるだけで、他の設定は全部
読まれる（実害は「Ctrl+Enter が効かない」だけ）。

**F13. PowerShell の managed block には既存の型がある**（deploy.sh で追記 → clean.sh の
`sed` で削除 → doctor.sh の marker 検査 → `tests/unit/`。ADR 0022/0024/0031/0033）。
本件では**使わない**（F8 の決定と却下案を参照）。

**F14. Terminal.app には拡張キーを送る手段が無い。** Apple の
"Change Profiles Keyboard settings" が示す設定項目は、Key 一覧（function key 用の
Add / Edit / Remove）、「Use Option as Meta key」、「Scroll alternate screen」だけで、
modifyOtherKeys / CSI-u に相当する送出は無い（iTerm2 の「Send Hex Code」に当たるものが
無い）。→ Ctrl+Enter の改行は Terminal.app では対象外とし、実機で **素の Enter と同じ
生バイト（`0d`）** であることを確認して確定する（確認できなければ「対象端末」に戻す）。

## 変更内容

### 1. `.zshrc` — 修飾キー付き矢印を束縛する

ctrl+enter ブロックの直後（EOF 側）に追加。

```
# Word movement. zsh's default emacs keymap binds only bare cursor keys
# (Src/Zle/zle_keymap.c: add_cursor_key), so the xterm forms for
# modifier+arrow were unbound and echoed as garbage. Ghostty pins Option+arrow
# to ESC b/f (tools/ghostty-config), so the Alt form here is for iTerm2;
# Ctrl+arrow is what Windows Terminal leaves alone (its defaults claim
# alt+left/right for pane focus).
bindkey '^[[1;3D' backward-word # Option+left
bindkey '^[[1;3C' forward-word  # Option+right
bindkey '^[[1;5D' backward-word # Ctrl+left
bindkey '^[[1;5C' forward-word  # Ctrl+right
```

- Ctrl+←/→ を足すのは利用者の選択（Windows/WSL で WT に取られないキー）。
  `.zshrc` は macOS と WSL で共有なので、macOS でも Ctrl+←/→ が効くようになる（整合的）。
- Shift+←/→（選択）は束縛しない。`select-word-style` も入れない（単語区切りは zsh 既定）。

### 2. `tools/ghostty-config` — Option+←/→ を明示的に固定

Keybind 節に追加（既存の ctrl+enter 行は変更しない）。

```
# Option+left/right: one word left/right (the docs' esc: example is esc:d =
# M-d). `esc:` sends an ESC-prefixed sequence and opt is an alias for alt;
# ESC b / ESC f are zsh's built-in backward-word / forward-word, so this keeps
# working inside tmux (see tools/tmux/tmux.conf).
keybind = opt+left=esc:b
keybind = opt+right=esc:f
```

### 3. `tools/tmux/tmux.conf` — extended keys を有効化

TrueColor ブロックの直後に追加（既存行は変更しない）。

```
# Extended keys (modifyOtherKeys): Ctrl+Enter inside a pane. The shipped file
# (tools/tmux/tmux.conf) carries the measured rationale; this block is only the
# spec for the two commands.
set -s extended-keys always
# tmux only asks the outer terminal for extended keys when it knows it is
# supported; this is the tmux wiki's Modifier-Keys line. Terminals that ignore
# the request are unaffected (tmux recognises extended keys regardless).
set -as terminal-features 'xterm*:extkeys'
```

### 4. `USAGE.md` — 「キー操作」の表に追記

| キー | 動作 |
| --- | --- |
| `Ctrl+Enter` | 改行する（送信はしない。Ghostty / iTerm2 で、tmux の中でも効く） |
| `Option+←` / `Option+→` | 1 単語戻る / 進む |
| `Ctrl+←` / `Ctrl+→` | 1 単語戻る / 進む（Windows Terminal が Alt+矢印を使うので Windows と WSL はこちら） |

表の直後に 2 行:

- `Ctrl+Enter` を tmux の中で効かせるには tmux 3.2a 以降が要る
  （確認は `tmux -V`。未満だと警告が出るだけで他は動く）。
- 単語の区切りと止まる位置は zsh 既定のまま（Windows の PowerShell は PSReadLine 既定で、
  `Ctrl+→` の着地点が zsh と少し違う。端末ごとの差は `docs/plan/terminal-keys.md`）。

`USAGE.md` は「zsh の使い方」なので、シェル以外（PowerShell・Windows Terminal）の話は
この表の注記以上に広げない。

### 5. `docs/plan/terminal-keys.md`

本文書。「GUI 手順」と「実機確認」の節を末尾に置く。

### 6. `README.md` は変更しない

deploy の挙動が変わらないため（PSReadLine block を採らないことは F8 の決定と却下案を
参照）。review 指摘 5 が挙げた README の更新は、この判断で解消する。

### 7. `tests/unit/test_terminal_word_movement.py`（新規、静的検査）

tmux / zsh / Ghostty のバイナリが無いホスト（native Windows）でも走る。

- `.zshrc`: 4 つのシーケンス `^[[1;3D` / `^[[1;3C` / `^[[1;5D` / `^[[1;5C` の **それぞれに
  ついて** `bindkey '<seq>' <widget>` の行がちょうど 1 本あることを見る（widget は
  `backward-word` / `forward-word`）。既存の Ctrl+Enter の `bindkey` 2 行や他の
  `bindkey` を数に入れない（全 `bindkey` 行の総数を数えると PR #452 の行と衝突する）。
  加えて `^[[1;2` / `^[[1;4`（Shift 系）が無いこと。
- `tools/ghostty-config`: `keybind = opt+left=esc:b` と `keybind = opt+right=esc:f` が
  1 回ずつあること。
- `tools/tmux/tmux.conf`: **コメント行を除いた**実コマンド行に対して、
  `set -s extended-keys always` と `terminal-features` の `extkeys` が 1 回ずつあり、
  `xterm-keys` と `extended-keys-format` の行が **無い** こと（コメントには
  `xterm-keys` という語が正当に出るので、素の substring 検索は使わない）。
  さらにコメントに `3.2a` があること（前提の明示を artifact に固定する）。
- PR #452 の ctrl+enter ブロックが残っていることは既存の
  `tests/unit/test_zshrc_ctrl_enter.py` が見ている。

## GUI 手順（リポジトリで配れない部分）

### Terminal.app

- 追加設定は不要（F10。Option+←/→ が既定で単語移動）。
- Ctrl+Enter の改行は対象外（F14）。実機で CR のままであることを確認する。

### iTerm2（使う場合）

- Profiles → Keys で ⌥← / ⌥→ に "Send Escape Sequence" を割り当て、それぞれ `b` / `f`
  （既定の送出形は環境依存なので、端末任せにせず明示する）。
- Ctrl+Enter を改行にしたい場合は、同じ Keys で `^⏎` に "Send Hex Code" を割り当てて
  `0x1b 0x5b 0x32 0x37 0x3b 0x35 0x3b 0x31 0x33 0x7e`（= `^[[27;5;13~`。`.zshrc` が
  既に束縛している形）を送る。

### Windows（Windows Terminal + PowerShell / WSL）

- 追加設定は不要。Ctrl+←/→ は WT が束縛していないのでそのまま届き、PowerShell は
  PSReadLine 既定で単語移動、WSL の zsh は本変更の `.zshrc` で動く（F8・F9）。
- Alt+←/→ を Windows でも使いたい場合だけ、WT の Actions で `alt+left` / `alt+right` を
  Unbound にし、`$PROFILE` に PSReadLine の 2 行を足す。**今はやらない**（自動化しない）。

## 検証

### このホストで確認済み（native Windows）

- F8: PSReadLine の既定束縛と Alt+矢印の追加が効くことを pwsh で実行確認
  （`Get-PSReadLineKeyHandler` で読み戻し）。
- F9: Windows Terminal の `defaults.json` を取得して `alt+left/right` →
  `Terminal.MoveFocusLeft/Right` を確認し、このホストの `settings.json` に上書きが
  無いことも確認。
- 変更後の自分のテスト: **`just check`（ROOT_AGENTS が求める完了ゲート）** を回し、
  追加で unit テストを含む `just ci` も回す。doc の markdown は
  `markdownlint-cli2` 単体でも先に確認する。

### 実機（macOS / tmux / 各端末）で確認が必要な点 — マージ前のゲート

1. `tmux -V` が 3.2a 以上（回答済み。実測値を PR 本文に記録する）。
2. tmux 内のペインで `cat -v`:
   Option+← → `^[b`、Ctrl+← → `^[1;5D`、Ctrl+Enter → `^[[27;5;13~`。
   加えて zsh のプロンプトで Ctrl+Enter が **送信されず改行になる**（`ls` を打ってから
   Ctrl+Enter → まだ実行されない）。これが本件の本当の合格条件。
3. tmux の外（Ghostty）の `cat -v` で Option+← → `^[b`（keybind が発火すること）。
4. tmux の設定値: `tmux show -s extended-keys` → `always`、
   `tmux show -s terminal-features | tr ',' '\n' | grep extkeys`。
5. Terminal.app（tmux の内外）で `cat -v`: Option+← が単語移動になること
   （`^[b` か、端末側で処理されて移動するか）。Ctrl+Enter は **`^[` で始まる並びが
   出ない** こと（下の「生バイトの見方」で `Enter` と同じ `0d` であることまで見る）。
   これが F14 の確定。
6. iTerm2 を使う場合（tmux の内外）: ⌥← → `^[b`、Ctrl+Enter → `^[[27;5;13~`。
7. 「Use Option as Meta key」が現在どうなっているか（Terminal.app を併用する場合）。
   F10 により、切っていても Option+←/→ は効くはず。

### 生バイトの見方（Ctrl+Enter と Enter の区別だけ raw で見る）

`cat -v` は cooked tty で動くので、**CR は ICRNL で NL に変換されて消える**（素の
Enter も、拡張キー非対応の Ctrl+Enter も、同じ改行に見える）。ESC で始まる並びは
変換されないので `cat -v` で見えるが、`0d` かどうかの判定は raw で読む。

```bash
# 1 バイトだけ読んで即座に戻る（ハングしない）
stty raw -echo; dd bs=1 count=1 2>/dev/null | od -An -tx1; stty sane
```

- 素の Enter /（端末直下で）拡張キー非対応の Ctrl+Enter → `0d`（F14 の Terminal.app 等）
- 拡張キー対応の Ctrl+Enter → `1b`（ESC。残りのバイトはプロンプトに残るので `Ctrl+U`）
- **tmux の中は別**: `extended-keys` の行が無い既定 off は **バージョンで結果が違う** —
  tmux 3.4 は何も届かず（`0d` ではない）、3.7c は `0d`（= Enter と同じ）。何も出ない
  と `dd` は待ち続けるので、普通の Enter か `Ctrl+C` を押せば 1 バイト読んで戻る
  （`stty raw` 中は `Ctrl+C` が SIGINT にならず 1 バイトとして届く）

つまり **「Ctrl+Enter が `0d` を出す」= Enter と区別できない** が結論で、`^M` が見える
ことは期待しない（見えたら ICRNL が切れている別の状態）。生バイトを見るなら tmux の外
（端末直下）が確実で、tmux の中は上記のとおりバージョンで挙動が違う（3.4 は何も出ない、
3.7c は `0d`）。

**F4 の mode 1 の読みが外れていた場合**（Option+← が `^[[27;3;68~` のような別形で
届く）は、その形を `.zshrc` に追記する。`extended-keys on` に落とす選択肢もあるが、
Ctrl+Enter が効かなくなるので取らない。

**マージ方針:**

- PR 本文にこの 7 点をチェックリストとして載せる（未確認のまま「動く」と主張しない）。
- **エージェントはマージしない。** PR を出したら停止し、利用者とレビュアーのレビューを
  待つ。マージの指示が出るまで、CI が全部緑でも squash merge しない。

## 却下した代替案

| 案 | 却下理由 |
|---|---|
| `$PROFILE` に PSReadLine の Alt+←/→ block を足す | F9。WT が alt+left/right を pane 移動に使うので PSReadLine に届かない。WT が束縛していない Ctrl+←/→ は **既定で既に効く**（F8）ので、Windows 側は何もしないのが正しい |
| `$PROFILE` で `Ctrl+RightArrow` を `ForwardWord` に上書きして着地点を揃える | 動いている Windows 既定を配布物で上書きしない（F8 の決定）。必要になったら 1 行 + 既存の managed block の型（F13）で足せる |
| WT の `settings.json` を repo で管理して `unbound` を書く | JSONC + GUID だらけの GUI 管理ファイルで、他の設定と同じ marker 方式が使えない。手順の文書化に留める |
| `setw -g xterm-keys on` を足す | F2。no-op で誤解を招く |
| `extended-keys on` を使う | F4（3.5 以降の man）。zsh は要求しないので Ctrl+Enter が素の CR のまま |
| `extended-keys-format csi-u` に変更 | F5。既定 xterm の `^[[27;5;13~` は既に `.zshrc` が束縛済み。利益ゼロ・検証不能なリスク |
| `default-terminal` を `tmux-256color` に | 本目的に無関係。terminfo 不在リスクだけ増える |
| `%if` でバージョン分岐 / doctor に tmux の版チェック | F12 により 3.2a 未満の実害は警告 1 行 + 機能が効かないことだけ。`%if` は tmux 2.4 以降でしか解釈されず、比較の format 演算子も版依存なので、古い tmux を守るつもりが別の壊れ方をする。前提はコメントと USAGE.md に明示する方針に寄せた |
| Terminal.app の「Option キーを Meta キーとして使用」を案内 | F10。Apple 公式が Option+←/→ を単語移動として挙げ、Meta の注記を付けていない。Option 全体を Meta 化する副作用を勧める必要がない |
| Terminal.app も Ctrl+Enter の対象にする | F14。端末から拡張キーを送る手段が無い。実機確認 5 で確定する |
| Ghostty の既存 ctrl+enter 行を `csi:13;5u` へ書き換え | byte 同一。マージ済みで利用者が実機確認済みの行を触る価値がない |
| `just terminal-keys-probe` recipe を足す | 実機確認は人間がキーを押して `cat -v` を見るしかなく自動化できない。実行するコマンド（`cat -v`、`tmux show -s …`）を本文書に列挙するに留める |
| Ctrl+←/→ も「macOS では不要」として足さない | F1 により Windows/WSL では未束縛。WT が取らないキーで、利用者もそれを選んだ |
| `docs/plan/` ではなく独立した runbook を新設 | 計画と手順が二重になる。本文書に統合する |

## リスクと緩和

- **F4（mode 1）の読みが違うと、tmux 内で Option+← が化ける。**
  → 実機確認 2 で 5 秒で判定できる。別形だった場合の対処も用意。
- **`terminal-features 'xterm*:extkeys'` が modifyOtherKeys 非対応端末を巻き込む。**
  → tmux は要求を送るだけで、無視する端末は従来どおり legacy を送る。tmux 自身は
  拡張キーを常に認識する（F4）。upstream wiki の推奨行でもある。
- **3.2a 未満の tmux で警告が出る。** → F12 により非致命的。前提はコメントと
  USAGE.md に書く。
- **Ctrl+Enter が使える端末が Ghostty / iTerm2 に限られる。** → 目的をそこで切っている
  ので「どこでも改行」とは主張しない。USAGE.md の表にも端末名を書く。
- **Ghostty の `opt+left=esc:b` が既存 keybind と衝突する。** → テストが「1 回ずつ」を
  見るので二重定義は検出できる。
