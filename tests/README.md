# tests/

テストは、Docker の要否で 2 つに分かれる。

| 場所 | 内容 | 実行 |
| --- | --- | --- |
| [`unit/`](./unit/) | Docker の要らないテスト。純粋な Python の関数と、ファイルの静的検査 | `just test-unit`（`just ci` に含まれる） |
| `tests/*.py` | Dev Container の image を使うサンドボックステスト | `just test`（先に image を作る） |
| [`docker/`](./docker/) | `just test-install` が使う `InstallTest.Dockerfile` | |

Docker が要らない静的検査は `unit/` に置く。
`tests/` の直下に置くと `just test` だけが拾い、`just ci` には乗らない。
e2e のディレクトリは無い。本物の依存を要する経路はこのリポジトリに残っていない。

## 実行

```bash
just test-unit                         # unit/ だけ（Docker 不要）
just test                              # サンドボックステスト全体
just test-mark marker=validate         # マーカーで絞る（install、validate、versions、deploy、check）
uv run pytest tests/unit/test_<name>.py   # 1 ファイル
```

## 書き方の決まり

テスト全般の決まり（mock の方針、given / when / then）は
[testing の spoke](../ROOT_AGENTS_docs_agents_testing.md) にある。このリポジトリ固有の決まりは次のとおり。

- unit のテストも、できるだけ本物のファイル、git、プロセスを使う。外部のサービス（gcloud、claude、npm など）は PATH に置いた stub で置き換え、`monkeypatch` は境界の I/O に限る。
- サンドボックステストは、既存の fixture（`docker_image`、`saved_image`）で 1 テストに 1 つの `--rm` コンテナを使う。
- `just test` はホストから実行する。サンドボックスは mount した tree で `git init` と `.git/info/exclude` の上書きを行うので、ホストでは使い捨ての snapshot を mount する。checkout をそのまま bind mount できるのは、`DOTFILES_SANDBOX_DISPOSABLE_CHECKOUT=1` で使い捨てだと宣言した CI だけで、それ以外（Dev Container の中からの実行など）は `_mount_mode` が拒否する。
- Docker に届かないときは `pytest.skip` する。Docker のない機体でも残りは通る。

## Windows で動かす

`unit/` は native Windows（日本語版、cp932）でも全部通る状態を保つ。

- テキストの読み書きには `encoding="utf-8"` を、subprocess の `text=True` には `encoding="utf-8", errors="replace"` を渡す（`unit/test_text_io_encoding.py` が検査する）。
- シェルの stub を書くときは `newline="\n"` を渡す（CRLF のままでは bash が読めない）。
- ネイティブのプロセスから bash を起動するときは `unit/_bash_hook.py` の `resolve_bash()` を使い、bash に渡す PATH の要素は `bash_path()` で `/c/...` の形にする。
- POSIX のファイルモード（0600、実行ビット）のように Windows で表せない検査だけを skip する。

## 関連文書

- [`../docs/runbook/windows-host.md`](../docs/runbook/windows-host.md)：native Windows の罠
