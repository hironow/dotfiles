# zsh の使い方

Sheldon と Starship を使った、fish に近い操作感の zsh の設定（Mac、Linux、WSL）。

## 準備

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
