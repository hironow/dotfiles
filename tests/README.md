# tests/

テストは、Docker の要否で 2 つに分かれる。

| 場所 | 内容 | 実行 |
| --- | --- | --- |
| [`unit/`](./unit/) | Docker の要らないテスト。純粋な Python の関数と、ファイルの静的検査 | `just test-unit`（`just ci` に含まれる） |
| `tests/*.py`、[`exe/`](./exe/) | Dev Container の image の中で動かすサンドボックステストと、exe.hironow.dev の IaC の検査 | `just test`（先に image を作る） |
| [`e2e/exe/`](./e2e/exe/) | 実際のクラスタに対する exe の停止経路。`EXE_E2E=1` のときだけ動く（`just exe-e2e` は digest で固定した `EXE_E2E_IMAGE` と `EXE_E2E_FORCED=1` も要る） | `just exe-e2e`（[README](./e2e/exe/README.md)） |
| [`docker/`](./docker/) | 重い exe のテストが使う Dockerfile | |

Docker が要らない静的検査は `unit/` に置く。
`tests/` の直下に置くと、`just test` だけが拾い、`just ci` には乗らない。

## 実行

```bash
just test-unit                         # unit/ だけ（Docker 不要）
just test                              # サンドボックステスト全体
just test-mark marker=validate         # マーカーで絞る（install、validate、versions、deploy、check）
uv run pytest -m exe                   # 重い IaC のテスト（@pytest.mark.exe）だけ
uv run pytest tests/unit/test_<name>.py   # 1 ファイル
```

## 書き方の決まり

- e2e のテストは本物の依存だけを使う（mock しない）。本物を使えないテストは unit か結合テストに置く。
- unit のテストも、できるだけ本物のファイル、git、プロセスを使う。外部のサービス（gcloud、coder、npm など）は PATH に置いた stub で置き換え、`monkeypatch` は境界の I/O に限る。
- サンドボックステストは、既存の fixture（`docker_image`、`saved_image`）で 1 テストに 1 つの `--rm` コンテナを使う。
- 準備が込み入るテストは、本文を given / when / then で区切る。
- Docker に届かないときは `pytest.skip` する。Docker のない機体でも残りは通る。

## Windows で動かす

`unit/` は native Windows（日本語版、cp932）でも全部通る状態を保つ。

- テキストの読み書きには `encoding="utf-8"` を、subprocess の `text=True` には `encoding="utf-8", errors="replace"` を渡す（`unit/test_text_io_encoding.py` が検査する）。
- シェルの stub を書くときは `newline="\n"` を渡す（CRLF のままでは bash が読めない）。
- ネイティブのプロセスから bash を起動するときは `unit/_bash_hook.py` の `resolve_bash()` を使い、bash に渡す PATH の要素は `bash_path()` で `/c/...` の形にする。
- POSIX のファイルモード（0600、実行ビット）のように Windows で表せない検査だけを skip する。

## 関連文書

- [`../README.md`](../README.md)：リポジトリの概要
- [`../docs/adr/`](../docs/adr/)：テストが守っている設計判断
- [`../docs/runbook/windows-host.md`](../docs/runbook/windows-host.md)：native Windows の罠
- [`../exe/docs/architecture.md`](../exe/docs/architecture.md)：`exe/` のテストが対象とする構成
