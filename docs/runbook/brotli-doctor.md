# Brotli doctor

`just brotli-doctor` は、導入済みCLIのバイナリからBrotliに関する証拠を集める。
CVEの影響判定や「Brotliが含まれない」という保証は行わない。
証明書の診断は [ca-doctor](ca-doctor.md) を使う。

## 実行方法

ビルドには導入済みのGo 1.27以降が必要。
診断中にコンパイラやパッケージをインストールしない。
コードを更新したら再ビルドする。

```bash
just brotli-doctor-build
just brotli-doctor
just brotli-doctor --json
```

既定の走査範囲は次のとおり。

- `mise ls --installed --json` が返す全導入版の配置先を再帰走査する。非アクティブ版も含む。
- PATHの各ディレクトリは直下だけを調べる。symlinkで別ディレクトリへ再帰しない。
- Unixでは実行ビットのある通常ファイル、Windowsでは `.exe` または `.com` の通常ファイルを候補にする。
- 候補のうちELF、Mach-O、PEを解析する。スクリプトやラッパーは実行せず、非ネイティブとして数える。

mise配下から外へ出るsymlinkは除外して未完了を報告する。
PATH直下のファイルsymlinkは実体を調べ、同じ実体を重複解析しない。
ホーム全体、その祖先、ファイルシステムのルートをmiseの再帰走査先として受け付けない。
空または相対パスのPATH要素も除外して報告する。
mise自体はPATHから起動するため、PATHとmiseは信頼できるものを使う。

対象を狭める場合は次のように実行する。
ファイル指定時はmiseもPATHも走査しない。

```bash
just brotli-doctor --mise=false
just brotli-doctor --path=false
just brotli-doctor '/path/with spaces/tool'
just brotli-doctor --json ./output/brotli-doctor/brotli-doctor
```

`--max-bytes` は1ファイルの解析上限で、既定値と最大値は512MiB。
上限超過、読み取り失敗、解析失敗、走査打ち切りは未完了になる。
走査項目は最大200,000件、miseの出力は最大8MiB。
`--timeout=2m` は走査と文字列読み取りの協調的な期限であり、ファイルI/Oを強制中断する保証ではない。
変更され続けるディレクトリの一貫したスナップショットや、敵対的な同時ファイル差し替えに対する隔離は提供しない。

## 出力の読み方

| 表示 | 意味 |
| --- | --- |
| `dynamic-import` | 直接のimportにBrotli名のライブラリがある。実際に解決されるパスと導入版を確認する |
| `c-defined-symbol` | 定義済みC API名がある。Cコード内包の手掛かりだが、静的リンクや実際の呼び出しの確定ではない |
| `c-undefined-symbol` | 未定義C API名がある。供給元は別途確認する |
| `go-build` | Goのビルド版。これ単独ではBrotliの証拠にならない |
| `go-module` | Brotli名のGoモジュールの記録。置換先があれば併記する |
| `c-api-string` / `rust-path-string` | 文字列の手掛かり。リンク方式、Rustクレート版、使用実態は確定できない |
| `UNKNOWN` | 当該アーキテクチャでBrotliの証拠を取得できなかった。未使用という意味ではない |
| `HINT` | 文字列の手掛かりだけがある |
| `EVIDENCE` | import、シンボル、モジュールの証拠がある。脆弱という意味ではない |
| `INCOMPLETE` | 走査または解析の一部が完了していない。JSONでは `incomplete: true` |

Pure Goに対応するモジュール名やPure Rustらしい文字列があっても、同じバイナリにC実装が共存しうる。
動的リンクが見つかっても、別途静的リンクされたコピーの不在は保証できない。
fat Mach-Oは各スライスを別々に扱い、対応できない形式や壊れたスライスは未完了として報告する。

終了コードは0が解析完了、1が未完了、2が引数エラー。
**0を脆弱性検査の合格条件として使わない。**
非ネイティブなラッパーしか見つからない場合も、正常に走査できれば0になる。

## 影響調査と更新

直接importは、そのライブラリがさらに読み込むライブラリまで追跡しない。
`dlopen`、PEのdelay-load、stripや最適化で消えた情報、スクリプトの実行先、コンテナ内の別環境も自動追跡しない。
Goのビルド情報が読めない場合やRustのクレート版が不明な場合は、ビルド記録、lockfile、SBOMを照合する。

CVEの対象実装と修正版を一次情報で確認してから更新する。
動的ライブラリを更新した場合、既に起動しているプロセスは再起動が必要になる場合がある。
影響を受けるコードを静的に含むバイナリは、依存更新後の再ビルドと置き換えが必要。
Pure実装もアルゴリズム由来の問題や独自の脆弱性を持ちうるため、C実装とは分けて調べる。
このコマンドは更新、再ビルド、再起動、ネットワーク経由のCVE照会を行わない。

## Bunの内包BrotliとCVE-2026-111497

2026-10-24に確認した公式情報では、Bun 1.4.4はこの修正を取り込んだリリースである。
根拠は次のとおり。

- [提案PR #46351](https://github.com/oven-sh/bun/pull/46351) は、C版Brotliへの修正に加えてRustのFFI enumに `ERROR_FORMAT_BLOCK_SWITCH = -17` を追加し、Rust側のエラー変換も変更する。このPR自体は確認時点で未マージ。
- 実際の取り込みは [マージ済みPR #46392](https://github.com/oven-sh/bun/pull/46392)（`2a5cbbcb084770dec7d7e2f21cdfd4f7f49b1ee3`）によるBrotli 1.2.1への更新。このコミットをbase、Bun 1.4.4の解決済みコミット `38afee6c84fcf48c0edb2466aa4b27d287a59c30` をheadとする [比較](https://github.com/oven-sh/bun/compare/2a5cbbcb084770dec7d7e2f21cdfd4f7f49b1ee3...38afee6c84fcf48c0edb2466aa4b27d287a59c30) は `behind_by: 0` で、取り込みを確認できる。
- [Bun 1.4.4のビルド定義](https://github.com/oven-sh/bun/blob/38afee6c84fcf48c0edb2466aa4b27d287a59c30/scripts/build/deps/brotli.ts) はBrotli 1.2.1の `db24a98aed38a16de78cc05ca15cdd8dc2a0d92d` を指定し、Cソースをアーカイブへビルドする。[Rust側のFFI定義](https://github.com/oven-sh/bun/blob/38afee6c84fcf48c0edb2466aa4b27d287a59c30/src/brotli_sys/brotli_c.rs) にも新しいエラー値がある。
- [Brotli 1.2.1の公式リリース](https://github.com/google/brotli/releases/tag/v1.2.1) は、このCVEの境界外書き込みをセキュリティ修正として記載する。[1.2.0からの差分](https://github.com/google/brotli/compare/v1.2.0...v1.2.1) に修正コミット `b418fa81c48262a86a95332b0bc6d62c30aa78b6` が含まれる。

したがって「Rustには関係ない」という説明は不正確。
脆弱性の修正対象は内包されたCデコーダだが、Rust側も新しいFFIエラー値に対応する必要がある。

`bun build --compile` の生成物はランタイムを内包するため、ビルドホストのBun更新だけでは既存の生成物は変わらない。
修正を取り込んだランタイムで生成物を再ビルドし、配布先のバイナリを置き換える。
コンテナは、確認した修正版のタグとdigestをDockerfileへ反映して再ビルドし、通常のデプロイ手順で置き換える。
`latest` というタグや、ホストのBunの版だけを修正取り込みの証拠にしない。

診断は `Bun v...` または `bun-v...` の版文字列を候補として検出する。
出力の `runtime_reviews` は候補ごとに1.4.4との比較を示すが、`binary_identity` と `patch_status` は常に `unverified` のまま。
`below-reviewed-release-threshold` は候補が修正取り込み版より古いこと、`at-or-above-reviewed-release-threshold` は候補の数値がその版以上であることだけを示す。
実際のバイナリ内容や将来版の修正保持を保証しない。
バックポートされた旧版も、文字列だけで影響ありとは断定しない。

プレリリース、不正な版、256文字を超える版、読み取り中断中の版は `unverified-version` になる。
有効なbuild metadataは数値比較から除外し、候補文字列には残す。
複数の候補を見つけても最大版だけを選ばず、最大16個までそれぞれ表示する。
候補数の上限超過は未完了として報告する。
文字列がなければBun不在と判断せず、出所とビルド記録を照合する。

信頼できる実行環境では、担当者が次のコマンドで版を確認できる。
これらは `brotli-doctor` が自動実行するコマンドではない。

```bash
bun --version
# 実環境の名前に置き換えて実行する
# podman exec <container> bun --version
# kubectl exec <pod> -c <container> -- bun --version
```

実際の攻撃到達性は、`fetch()` のBrotliレスポンス展開、`node:zlib`、`DecompressionStream("brotli")` などの利用状況で別途確認する。
受信リクエストの `Content-Encoding: br` をプロキシで遮断しても、外部レスポンスの展開は防げない。
この診断だけから、サービスが脆弱な処理へ到達可能かを断定しない。

## 他OSへの配置

```bash
just brotli-doctor-build-all
```

Linux、macOS、Windowsの各amd64とarm64向けバイナリを `output/brotli-doctor/` に生成する。
対象OS用のファイルを `brotli-doctor`（Windowsは `brotli-doctor.exe`）という名前で同ディレクトリに置く。
WindowsのrecipeはGit Bashを経由するが、診断自体はネイティブのGoバイナリが行う。
既存の `just doctor` からは自動起動しない。
