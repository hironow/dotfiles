# tests/

テストは、コンテナの要否で分かれる。
実行エンジンは Podman 5+、Compose provider は podman-compose を使う。

| 場所 | 内容 | 実行 |
| --- | --- | --- |
| [`unit/`](./unit/) | コンテナ不要の関数・ファイル・プロセス境界検査 | `just test-unit`（`just ci` に含まれる） |
| `test_just_sandbox.py` など | 毎回専用 image を作り、実際の Dev Container up → exec と保存 image を検査 | `just test` |
| `test_install.py` / [`docker/`](./docker/) | 追跡ファイルだけの context と `InstallTest.Dockerfile` で通常セットアップを 2 回検査 | `just test-install` |

コンテナ不要の静的検査は `unit/` に置く。
`tests/` 直下の新しい検査は、表にある実行 recipe へ明示的に配線する。
実サービス・DB を使う e2e は [`../emulator/tests/e2e/`](../emulator/tests/e2e/) にある。

## 実行

```bash
just test-unit                         # unit/ だけ（コンテナ不要）
just test                              # 必須のサンドボックス検査
just test-mark validate                 # マーカーで絞る（install、validate、versions、deploy、check）
just test-install                      # 通常セットアップ 2 回と呼び出し tripwire
uv run --frozen --group dev pytest tests/unit/test_<name>.py  # 1 ファイル
```

## 隔離した emulator の CI 相当検査

`just ci-emu` は lint 後、専用 manifest で Firebase / Spanner / pgadapter / Postgres と
telemetry を prepare → start → wait し、CI と同じ non-e2e・e2e・Postgres 18 の検査を行う。
既存の Podman / podman-compose と emulator の uv 依存環境が必要で、ホストの導入処理は行わない。
実行は `emulator/` の frozen dev group を使い、`UV_PROJECT_ENVIRONMENT`、`UV_NO_SYNC`、
`UV_OFFLINE` の指定を保持する。ローカルの Docker 実行ファイルは移動・使用しない。

共有 stack の起動・削除は行わず、継承した `DOTFILES_PODMAN_RUN_MANIFEST` は拒否する。
通常終了・失敗時は同じ manifest の cleanup だけを呼ぶ。元の失敗を保持し、cleanup の失敗も成功扱いしない。
`.pi/tasks/ci-emu.*/run.json` と配下の snapshot / tmp はシェルから削除しない。
INT / TERM では競合する cleanup を開始せず、manifest を残して非ゼロで終了する。
SIGKILL でも資源が残り得る。**生成プロセスの停止を確認してから**、同時に回収を走らせず、
表示された manifest を指定して `emulator/` で次を実行する（共有の `emu-clean` は使わない）。

```bash
uv run --frozen --group dev python -m tests.utils.isolation cleanup --manifest /absolute/path/to/run.json
```

生成の終了が不明な journal を手で完了扱いにしたり、snapshot を先に削除したりしない。

## 書き方の決まり

テスト全般の決まり（mock の方針、given / when / then）は
[testing の spoke](../ROOT_AGENTS_docs_agents_testing.md) にある。このリポジトリ固有の決まりは次のとおり。

- unit のテストも、できるだけ本物のファイル、git、プロセスを使う。外部のサービス（gcloud、claude、npm など）は PATH に置いた stub で置き換え、`monkeypatch` は境界の I/O に限る。
- 既存の fixture 名 `docker_image` / `saved_image` は互換用であり、実際には毎回確認した Podman image の不変 ID を使う。
- `just test` はホストから実行し、追跡された作業ファイルだけの snapshot を使う。
  symlink・junction・Git 管理領域への経路を拒否し、実 checkout の `.git` は mount しない。
  一回限りの検査で checkout の bind を許すのは、`DOTFILES_SANDBOX_DISPOSABLE_CHECKOUT=1` と対応する engine-side path がある場合だけ。
  完全な up → exec 検査は、snapshot を実 Git ancestry の外に置くため、入れ子の Dev Container 起動を拒否する。
- 選択中 engine の socket と操作権限については [Dev Container の手順](../.devcontainer/README.md) を読む。
  socket は engine 操作権限を与えるため、完全隔離された security sandbox とは扱わない。
- 必須の CLI・接続・build・runtime の失敗を `pytest.skip` で成功扱いにしない。
  終了が不明な生成操作は journal を未完了のまま保持し、空の inventory だけで終了済みと判断しない。
  回収はこの実行が記録・確認した resource / tag に限り、共有 stack や他の image alias を削除しない。

## Windows で動かす

`unit/` は native Windows（日本語版、cp932）でも全部通る状態を保つ。

- テキストの読み書きには `encoding="utf-8"` を、subprocess の `text=True` には `encoding="utf-8", errors="replace"` を渡す（`unit/test_text_io_encoding.py` が検査する）。
- シェルの stub を書くときは `newline="\n"` を渡す（CRLF のままでは bash が読めない）。
- ネイティブのプロセスから bash を起動するときは `unit/_bash_hook.py` の `resolve_bash()` を使い、bash に渡す PATH の要素は `bash_path()` で `/c/...` の形にする。
- POSIX のファイルモード（0600、実行ビット）のように Windows で表せない検査だけを skip する。

## 関連文書

- [`../docs/runbook/windows-host.md`](../docs/runbook/windows-host.md)：native Windows の罠
