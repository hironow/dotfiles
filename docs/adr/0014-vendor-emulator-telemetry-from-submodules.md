# 0014. Vendor emulator and telemetry from submodules into dotfiles

**Date:** 2026-05-30
**Status:** Accepted

## Context

`emulator` (hironow/emulator-set) と `telemetry` (hironow/telemetry-set) は git
submodule として dotfiles に取り込まれていた。両者は「初期開発道具一式」として
dotfiles と一貫して使う対象であり、 別リポジトリ submodule 運用には摩擦があった:

- pointer 更新 / `git submodule update --remote` の二段手順、 detached HEAD 運用
- dotfiles 単体 clone では中身が空になり、 初期セットアップに段差が出る
- 自分が単一の書き手である自前 repo であり、 別 repo に分離する利点が薄い

## Decision

両者を submodule から通常の git 管理ファイルへ移行 (vendoring) し、 dotfiles を
単一の真実源とする。 upstream repo (emulator-set / telemetry-set) は archive 扱い。

- `.gitmodules` / `.git/config` / `.git/info/exclude` から両 path を除去
- 作業ツリーの実ファイルを追加 (nested `.gitignore` を尊重し、 秘密=`.env.local` /
  巨大=`mlflow.db` / データ=`*-data` は除外継続)
- vendored sub-project は内部の `pyproject.toml` / `tests/` / `scripts/` を
  自己完結で保持する一方、 orchestration (justfile recipe)・CI・semgrep ルールは
  root に集約する。 CLAUDE.md project-structure の「外部由来 (submodule/cloned)
  tree は root 単一化ルールの例外」に準ずる運用とする。

## Consequences

### Positive

- 単一 clone で全道具が揃い、 submodule の二段更新が不要になる
- root justfile (`emu-*` / `tel-*`) から一貫操作でき、 CLAUDE.md「root 唯一の
  justfile」規約に整合する

### Negative

- upstream repo と dotfiles が乖離する (以後 dotfiles 側を正とする)
- vendored 分だけ dotfiles repo が肥大する (約 15.8k 行)

### Neutral

- root ruff は `pyproject.toml` の extend-exclude、 root の shell/markdown lint は
  `git ls-files` の pathspec (`':!emulator' ':!telemetry'`) で vendored tree を除外。
  vendored 固有の lint は `just emu-lint` が担当する
