# zsh の使い方

Sheldon と Starship を使った、fish に近い操作感の zsh の設定（Mac、Linux、WSL）。

## 準備

Linux と WSL では、先に zsh を入れてログインシェルにする（macOS は最初から zsh）。
`install.sh` は sudo を使わないので、zsh がなければ入れ方を表示するだけである（`just doctor` も同じく知らせる）。

```bash
sudo apt-get install -y zsh && chsh -s "$(command -v zsh)"   # Linux と WSL だけ
```

新しいターミナルを開いてから、次を実行する（sheldon は mise が入れる）。

```bash
just deploy   # 設定を配置する
sheldon lock  # 初回だけ: plugin を入れる
```

## キー操作

| キー | 動作 |
| --- | --- |
| `Ctrl+R` | 履歴をあいまい検索する（fzf） |
| `Tab` | プレビューつきであいまい補完する（fzf-tab） |
| `<` / `>` | fzf-tab の補完グループを切り替える |
| `Ctrl+Enter` | 改行する（送信はしない。Ghostty / iTerm2 で、tmux の中でも効く） |
| `Option+←` / `Option+→` | 1 単語戻る / 進む |
| `Ctrl+←` / `Ctrl+→` | 1 単語戻る / 進む（Windows Terminal が Alt+矢印を使うので Windows と WSL はこちら） |

`Ctrl+Enter` を tmux の中で効かせるには tmux 3.2a 以降が要る（確認は `tmux -V`。未満だと警告が出るだけで他は動く）。単語の区切りと止まる位置は zsh 既定のままで、Windows の PowerShell は PSReadLine 既定のため `Ctrl+→` の着地点が少し違う。

端末ごとの設定:

- Ghostty: 設定は要らない（`tools/ghostty-config` が `Option+←` / `Option+→` を単語移動に固定する）。
- Terminal.app: `Option+←` / `Option+→` は設定なしで単語移動になる。拡張キーを送れないので、`Ctrl+Enter` の改行は効かない。
- iTerm2: Profiles → Keys で `⌥←` / `⌥→` に "Send Escape Sequence" の `b` / `f` を割り当てる。`Ctrl+Enter` を改行にするには、`^⏎` に "Send Hex Code" で `0x1b 0x5b 0x32 0x37 0x3b 0x35 0x3b 0x31 0x33 0x7e`（`^[[27;5;13~`）を割り当てる。
- Windows Terminal（PowerShell と WSL）: 設定は要らない。`Alt+←` / `Alt+→` は Windows Terminal がペインの移動に使うので、`Ctrl+←` / `Ctrl+→` を使う。

## alias と関数

| 名前 | 実体 |
| --- | --- |
| `k` | `kubectl` |
| `j` | `just` |
| `mx` | `mise exec --` |
| `mr` | `mise run` |
| `cc` | `RUNOPS_ACTOR_TYPE=ai-agent claude` |
| `j-cc` / `j-pi` | Jev で思考レベルを選んで Claude Code / Pi を起動する（[手順](docs/runbook/jev-launchers.md)） |

## キャッシュ

起動を速くするため、次のキャッシュを作る。
道具を更新したら `just clean-cache` で消し、`sheldon lock` を実行し直す（`just clean-all` は配置した設定も消す）。

| キャッシュ | 用途 |
| --- | --- |
| `~/.cache/zsh/kubectl_completion.zsh` | kubectl の補完 |
| `~/.cache/zsh/fzf_init.zsh` | fzf のキー操作と補完 |
| `~/.zcompdump*` | zsh の補完 |
| `~/.local/share/sheldon/` | Sheldon の plugin |
| `~/.local/share/fzf-tab/` | fzf-tab |

## 起動時間

目標は 300ms 未満である。

```bash
time zsh -i -c exit
```
