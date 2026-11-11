# ADR 0072 — ローカルの telemetry は上流の grafana/otel-lgtm 1 つにする

- **id**: ADR-0072
- **title**: ローカルの telemetry は上流の grafana/otel-lgtm 1 つにする
- **status**: Proposed
- **date**: 2026-11-11
- **decided-date**: —
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code（owner session、Windows 機）
- **author-contact**: @hironow
- **supersedes**: [ADR-0014](0014-vendor-emulator-telemetry-from-submodules.md) の一部（telemetry/ の中身を vendored な sub-project として持つことと、その lint の除外だけ。emulator の vendoring は変えない）
- **superseded-by**: none
- **related**: [0003](0003-actions-pin-sha.md)、[0015](0015-adopt-portless-for-local-dev-urls.md) と後継 [0054](0054-run-portless-directly.md)、[0028](0028-flatt-pypi-mirror-default-index.md) と後継 [0053](0053-stop-using-flatt-mirrors.md)、[0065](0065-kernel-cve-is-evidence-only.md)、[0067](0067-use-podman-for-managed-containers.md)
- **consultation-trace**: 2026-11-11 の本セッションでの所有者の指示と選択（下の「相談の記録」）。同じ内容を公開 PR に残す

## やさしい説明

ローカルで traces・metrics・logs を見る仕組み（telemetry）を、自前の 5 つのコンテナと設定ファイルから、Grafana が配る `grafana/otel-lgtm` の 1 つのコンテナに替える。
設定・dashboard・例のアプリは持たず、上流の既定のまま使う。
emulator の metrics を集める仕組みと、そのための exporter もやめる。

## Context

- 所有者は 2026-11-11 に「<https://github.com/grafana/docker-otel-lgtm> を使うようにして、わたしたち独自のテレメトリの仕組みを入れるのはやめよう」と指示した。
- ADR-0014 は telemetry-set を submodule から vendoring し、自己完結の sub-project（pyproject・tests・scripts）として持つとした。root の lint は pathspec で telemetry/ を外した（0014 の Neutral）。
- 変更前の `telemetry/` は 20 ファイルだった。otel-collector・Tempo・Prometheus・Loki・Grafana の compose、各 config、Grafana の provisioning と 2 つの dashboard（Emulator Metrics を含む）、FastAPI の例（uv project）、docs。collector は emulator の `elasticsearch-exporter`・`postgres-exporter`・Qdrant の `/metrics` を scrape していた。
- `grafana/otel-lgtm`（Apache-2.0）は OpenTelemetry Collector・Prometheus・Tempo・Loki・Pyroscope・Grafana を 1 つの image にまとめる。上流は開発・デモ・試験用で、本番用ではないと明言している。
    - v0.39.0（2026-10-30 公開）の Dockerfile: `EXPOSE 3000 3200 4040 4317 4318 9090`、`HEALTHCHECK --interval=30s CMD /otel-lgtm/docker/healthcheck.sh`。データは `/data`。
    - v0.40.0 は 2026-11-06 公開で、2026-11-11 には 7 日の cooldown の中にある。
    - 2026-11-11 に `gh attestation verify --repo grafana/docker-otel-lgtm oci://docker.io/grafana/otel-lgtm:0.39.0 --signer-workflow grafana/shared-workflows/.github/workflows/sign-and-attest.yml` が exit 0 だった（subject の sha256 は `4c8056c9c05fcb3c8fd93800e85334bfd79b4d0271b47a54a121a64af41fe1fe`）。
- 2026-11-11 に GitHub の code search で、所有者が触れる repo を調べた。`shared-otel-net` を使うのはこの repo だけで、`otel-collector:4317` に送る container は見つからなかった（文字列はテストの値として 1 か所にあっただけ）。

## Decision

所有者の選択（emulator の metrics はやめる、例は消す、host の port は lgtm の既定に合わせる、exporter も消す）を、次の必須事項（MUST）として採択する。

- D1: `telemetry/compose.yaml` は service `lgtm` を 1 つだけ持ち、`docker.io/grafana/otel-lgtm:<X.Y.Z>` を使わなければならない（MUST）。リリースした版の tag で固定し、`latest` や `main` のような動く tag にしてはならない。
- D2: dotfiles は telemetry の config ファイル・dashboard・例のアプリを持ってはならない（MUST NOT）。`telemetry/` が追跡するのは `compose.yaml`・`README.md`・`.gitignore`（`.env` と `.env.local` だけを無視する）の 3 つとする。設定を変えるときは、上流が文書にした環境変数を使う。
- D3: host の port は lgtm と同じ番号で `127.0.0.1` だけに publish しなければならない（MUST）: 3000 Grafana、3200 Tempo、4040 Pyroscope、4317 OTLP gRPC、4318 OTLP HTTP、9090 Prometheus。
- D4: `shared-otel-net` を external の既定 network として残す。network の中の宛先は `lgtm:4317`・`lgtm:4318` とし、旧名 `otel-collector` の別名は置かない。
- D5: compose は上流と同じ healthcheck を書かなければならない（MUST）。隔離された検証（`tests.utils.isolation --telemetry`）は、lgtm が healthy になること、OTLP/HTTP の span が Tempo から読めること、Grafana が答えることを確かめる。`telemetry/**` の変更（`.md` を除く）でも Test Emulators の workflow が起動しなければならない。
- D6: image の版は Class 2 として 7 日の cooldown を置く。Dependabot の `docker-compose` ecosystem（`/telemetry`、`default-days: 7`）で上げ、merge の前に attestation を確かめる。
- D7: `just tel-down` は `down --remove-orphans` で、旧 stack の container も止めて消す。旧 stack の named volume は自動では消さない（README に手順を書く）。
- D8: emulator の `elasticsearch-exporter`・`postgres-exporter` と `exporters` profile を外す。
- D9: root の lint（ruff、markdownlint、prek、shellcheck と vp の pathspec）から telemetry/ の除外を外す。

## Options Considered

| 案 | 利点 | コスト・リスク | 裁定 |
| --- | --- | --- | --- |
| A) 上流の otel-lgtm 1 つにし、独自の設定を持たない（本案） | collector・backend・Grafana の設定と dashboard と例を保守しなくてよい。上流が組み合わせを試験した版を使う | emulator の metrics と dashboard が無くなる。host の port が変わる。上流は本番用ではない | 所有者が採択 |
| B) otel-lgtm にし、emulator の scrape と dashboard を config の mount で残す | emulator の metrics が見える | 独自の config と dashboard が残り、所有者の「独自の仕組みはやめる」に合わない。上流の config の形に追従が要る | 所有者が「やめる」を選んだため却下 |
| C) 今の 5 つのコンテナを保つ | 変更が無い | 所有者の指示を満たさない。5 つの image と config の保守が続く | 所有者の指示を満たさないため却下 |

## Consequences

- **Positive**: telemetry/ は 20 ファイルから 3 ファイルになる。image の版は Dependabot が cooldown を置いて上げ、attestation で出どころを確かめられる。隔離された CI が lgtm の実際の起動と OTLP の受け取りを確かめる。
- **Negative**:
    - host の port が変わる: Grafana 3010→3000、Prometheus 9091→9090。3000 はよくある開発サーバーと、9090 は Fedora の Cockpit とぶつかり得る。Loki（3100）、Tempo の Jaeger 受信（14268）、collector の自分の metrics・health・zpages（8888・8889・13133・55679）は host に出なくなる。
    - emulator の metrics（Elasticsearch・PostgreSQL・Qdrant）と Emulator Metrics の dashboard が無くなる。
    - `shared-otel-net` の上で `otel-collector:4317` に送っていた container は届かなくなる（2026-11-11 の検索では該当なし）。
    - 旧 stack の volume（`telemetry_grafana-data` など）は残り、手で消す。
- **Neutral**: emulator の vendoring（ADR-0014）は変えない。telemetry も submodule には戻さない。上流の OBI（eBPF の自動計装）は使わない。agent-baseline の Jaeger（`just trace-up`）はこの ADR の範囲外。portless の別名の一覧（0054）は、loki を外し pyroscope を足す。

## 反転記録 (Reversal)

- 反転はない。ADR-0014 の telemetry の分だけを部分置換する（0014 の本文は変えず、Status 行に置換先を書く）。

## 他の DR との照合

0001〜0071 の 70 件（0046 は欠番）の題名・状態・置換関係を走査し、telemetry・emulator・Dependabot・lint の除外・portless・Podman に触れる記録の全文を読んだ（0003、0014、0015、0028、0053、0054、0065、0067 ほか）。PDR はない。

- **矛盾**: 0014 の Decision（vendored な sub-project は自前の pyproject・tests を持つ）と Neutral（lint を pathspec で外す）は、telemetry について意図して置き換える（部分置換）。所有者は 0014 の決定者でもあり、本セッションで指示した。
- **重複**: 番号 0072 は未使用。同じ決定の記録はない。
- **誤読**: 0067 の Neutral「HTTP UI の URL と通常運用のポートは変えない」は、Podman への移行が port を変えないという結果の記述で、port を固定する規則ではない。0067 の「既存のデータは移行・停止・削除しない」も 0067 の PR の範囲の記述で、D7 は旧 volume を自動では消さない。
- **偽の関連**: 0028 と 0053 は `telemetry/examples` の取得元に触れていた。例を消すので、対象が無くなるだけで衝突しない。0065 の表の「telemetry のコンテナ」は 1 つになっても成り立つ。0003 の Dependabot は ecosystem を足す形で、衝突しない。
- **関係誤認**: 0054（portless の別名は docs の一覧に置く）は変えず、一覧の中身だけを直す。

## 相談の記録

- 2026-11-11、本セッションで所有者（@hironow、0014・0054・0067 の決定者）が指示し、次を選んだ: emulator の metrics の scrape と Emulator Metrics の dashboard は「やめる」、`telemetry/examples` は「消す」、host の port は「lgtm の既定に合わせる」、exporter は「今回いっしょに消す」。
- 計画は独立サブエージェントがレビューした（Codex はクレジット切れ）。lint の pathspec の除外、`tel-down` の orphan、healthcheck と e2e、`.env` の無視、cooldown、Test Emulators の paths、依存の洗い出しの方法を、その指摘から採った。

## 決定（記入待ち）

- [ ] A を Accepted（D1〜D9 を MUST 文で確定し、索引、変更ログ、queue を更新する）
- [ ] B を Accepted（emulator の scrape と dashboard を mount で残す）
- [ ] Rejected / Deferred（変更を戻し、queue に理由を残す）

決定者: Hiroto N.（@hironow）　決定日: —
