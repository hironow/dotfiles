# プロトコル変更ログ

最終更新: 2026-07-18

各プロトコル・Google Cloud サブモジュールの主要な変更点をまとめたドキュメント。

---

## プロトコル (Protocols)

### A2A (Agent-to-Agent)

**現行バージョン**: v1.0.1 (2026-05)

**チェックアウト状態**: `v1.0.1-24-gaf112d9` (v1.0.1 + 24 commits、 HEAD 2026-07-16。 新規リリースタグはなく v1.0.1 が依然最新)

#### 2026-07-18時点 新着 (spec 無変更、 community SDK 拡充のみ)

- **spec/version 変更なし**: v1.0.1 以降 HEAD まで全て docs/ci/chore、 behavioral 変更ゼロ
- **community SDK 拡充**: Rust SDK (a2a-rs) を追加 (#1863)、 C++ SDK (a2a-cpp) を community SDKs に追加 (#2034)
- **partners リスト更新**: AlgoVoi / Auto Agent Protocol / Lumika 追加、 broken link 除去

#### 2026-07-01〜2026-07-07 新着 (docs / CI のみ、 spec 変更なし)

- **パートナーリストに AlgoVoi 追加**: docs のみの変更 (#1994)
- **壊れたパートナーリンクを削除**: OIXA / Pinchwork のリンク切れエントリを除去 (#2017)
- **CI を buf-action へ移行**: 非推奨の buf-setup-action から移行 (#1999)
- **GitHub Actions 依存を 3 件まとめて更新** (#2035)

#### 2026-06-30 新着 (パートナーリストへの追加)

- **Auto Agent Protocol / Lumika をパートナーリストに追加 (docs のみ)**: `docs/partners.md` に Auto Agent Protocol (A2A の vertical) と Lumika (car dealership サイトへの A2A 統合を推進するパートナー) の2エントリを追加。 spec 変更・破壊的変更なし (#1907)

#### 2026-06-22 新着 (docs / CI のみ、 spec 変更なし)

- **docs build CI トリガー追加**: build inputs の変更で docs build を起動 (#1967)
- **`llms.txt` を v1.0 spec へ整合**: llms.txt を v1.0 spec とサイトナビゲーションに合わせて更新 (#1943)
- **ホームページバナー更新**: A2A ホームページのバナーを更新 (#1971)

#### 2026-06-12 新着 (ホームページ再構成)

- **ホームページ情報の再構成**: protocol overview のホームページ情報を再構成し、 欠落していたセクションを追加 (#1874)

#### v1.0.1 リリース (2026-05) 後の新着

- **v1.0.1 リリース**: v1.0.0 → v1.0.1 への正式リリース (#1749)
- **Rust SDK (a2a-rs) 参照追加**: README に Rust SDK (a2a-rs) リファレンス追加、 linter workflow 更新 (#1863)
- **multi-tenancy ガイド追加**: マルチテナンシーガイドと tenant フィールドのセマンティクス明確化 (#1848)
- **push notification auth 整合**: push notification 認証例をプロトコル挙動に整合 (#1793)
- **SDK 数を 6 に更新**: Rust 追加で公式 SDK 数を 6 に更新 (#1778)
- **Tutorial 8 import path 修正**: AgentExecutor import path 修正 (#1884)
- **MCP リファレンス明確化**: A2A overview の MCP 参照を明確化 (#1873)

#### v1.0.0 後の変更点

- **TaskStatus values 仕様修正**: TaskStatus values の仕様記述を修正 (#1801)
- **stateTransitionHistory 廃止参照削除**: 仕様から deprecated stateTransitionHistory references を削除 (#1834)
- **"Send Streaming Message" リネーム**: "Stream Message" → "Send Streaming Message"、レガシーメソッド名置換 (#1784)
- **HTTP binding MIME 推奨**: `application/a2a+json` を HTTP binding で優先使用 (#1753)
- **カスタムプロトコル bindings ドキュメント**: カスタムプロトコルバインディングの公式ドキュメント追加 (#1619)
- **新ロゴ＆マスコット**: ブランディング刷新 (#1719)
- **Community SDKs 追加**: 公式 SDK リストとは別に Community SDK セクション追加 (#1698)
- **Rust SDK 公式化**: 公式 SDK リストに Rust SDK 追加 (#1729)
- **TSC メンバー追加プロセス**: GOVERNANCE.md に TSC メンバー追加方法ドキュメント追加 (#1571)
- **仕様修正**: トランスコーディング関連エラーの修正 (#1627)
- **パートナーリスト拡充**: OIXA Protocol (#1692), Strale (#1702), WritBase (#1634) 追加
- **tutorial ホスト修正**: チュートリアルで `127.0.0.1` を使用 (#1783)
- **Python helloworld チュートリアル更新**: a2a-sdk v1.0 向けに更新 (#1775)
- **ローカルビルド手順**: Contributing Guide にローカルビルド手順追加 (#1726)

#### v1.0.0 の主要な変更点

- **正式リリース**: v1.0.0-rc から v1.0.0 への昇格
- **仕様リファクタ**: アプリケーションプロトコル定義とトランスポートマッピングの分離
- **Push Notification 統合**: `TaskPushNotificationConfig` と `PushNotificationConfig` の統合 (#1500)
- **フィールドリネーム**: `SendMessageConfiguration.blocking` → `return_immediately` (#1507)
- **HTTP エラーマッピング**: `google.rpc.Status` (AIP-193) 準拠の HTTP+JSON エラーマッピング (#1600)
- **LF パッケージプレフィックス**: LF パッケージプレフィックス追加 (#1474)
- **Extension ガバナンス**: Extension ガバナンスドキュメント追加
- **In-Task Authorization**: タスク内認可の詳細拡張
- **SDK 後方互換性**: SDK が後方互換可能な設計に

#### 破壊的変更（v0.3.0 → v1.0.0）

| 変更 | 影響 |
|------|------|
| ID形式簡素化: 複合ID → 単純UUID/リテラル (#1389) | リクエストID形式の変更 |
| Enum フォーマット: `lowercase` → `SCREAMING_SNAKE_CASE` (#1384) | 全Enum値の変更 |
| HTTP URL簡素化: `/v1/` プレフィックス削除 | エンドポイント URL の変更 |
| Well-Known URI: `agent.json` → `agent-card.json` (#841) | エンドポイント URL の変更 |
| OAuth implicit/password フロー削除 (#1303) | 認証フロー変更 |
| Push Notification Config 統合 (#1500) | 構造変更 |

#### 参考リンク

- [A2A Specification](https://github.com/a2aproject/A2A)

---

### A2UI (Agent-to-User Interface)

**現行バージョン**: production **v0.9.1** (安定版 v0.9 系 patch)。 **v1.0 spec は Release Candidate** (Status: Candidate, 2026-06-08)。 `v0.8`/`v0.9` 軽量タグは共に旧 commit 19919ef4 を指し spec version を表さない (実体は `specification/{v0_8,v0_9,v0_9_1,v1_0}/`)

**チェックアウト状態**: `7ebe771c` (v0.9 系 HEAD、 HEAD 2026-07-17。 2026-07-01 以降 71 commits と極めて活発、 新規リリースタグなし)

#### 2026-07-18時点 新着 (v1.0 RC 策定が加速。 破壊的変更は全て v1.0(RC) 対 v0.9 の差分で、 production v0.9.1 利用中は未影響)

- **v1.0 spec (RC) 策定**: 同期 client→server RPC (`actionResponse`+`actionId`)、 server→client の `callFunction`/`functionResponse` RPC、 実行境界を wire でなく runtime catalog で検証
- **createSurface 一括生成**: `components` と `dataModel` を createSurface payload 内に直接定義可能に。 `@index` builtin と UAX #31 識別子規則を追加
- **package release**: `@a2ui/web_core` v0.10.4 / `@a2ui/angular` v0.10.3 / Python `a2ui-core` v0.1.1 / `a2ui-agent-sdk` v0.4.0。 A2UI Elemental (compact HTML layout) 新設 (#1952)、 Swift SDK を production 構成へ

| 破壊的変更 (v1.0 RC vs v0.9) | 影響 |
|------|------|
| `theme` → `surfaceProperties` に改名、 `primaryColor` 削除 | layout と branding を分離。 createSurface/catalog 両方の改修 |
| MIME type `application/json+a2ui` → `application/a2ui+json` | transport 層のメディアタイプ更新が必須 |
| catalog `functions` が list → map (key=関数名) | 既存 catalog 定義の構造変換が必要 |
| icon `svgPath` → `path`、 識別子は UAX #31 準拠必須 | custom icon / 命名の修正 |

#### 2026-07-01〜2026-07-07 新着 (catalogId 明確化 + web_core 型エクスポート + Python ツーリング整備)

- **spec 明確化: `catalogId` は任意の文字列識別子**: 「解決可能な URI ではない」ことを v0.9 / v0.9.1 / v1.0 の各仕様で明確化。 well-known ID はクライアント/サーバ間の事前合意が前提と明記 (#1924)
- **web_core: `UserAction` を `ClientEventUserAction` として v0.8 でエクスポート**: 1P 利用向けの型エクスポート追加 (#1942)
- **API リネーム**: `indexSystemFunction` → `IndexSystemFunction` (#1811)
- **Angular 修正**: Angular signals を直接使用するよう修正 (#1733)、 Angular MCP Apps デモを A2UI v0_9 へ更新 (#1786)
- **Python ツーリング整備**: uv workspace 化 (#1814)、 PEP 420 名前空間パッケージ標準化 (#1815)、 `a2ui_core` の型チェック有効化 (#1816)、 pyink 設定集約 (#1911, #1932)、 Python CI 統合 (#1910)

#### 2026-06-29〜2026-06-30 新着 (v0.9.1 バリデータ修正 + Express コンパイラの脱ファイルシステム化 + Python 3.10 対応)

- **web_core: JSON Pointer エスケープ (RFC 6901) 対応**: TypeScript 版 `DataModel.parsePath` が `~1`→`/` / `~0`→`~` のアンエスケープを行うようになり、 Python SDK 実装とパリティを確保 (#1796)
- **Express コンパイラ suite の in-memory Catalog / A2uiCatalog 対応**: `CatalogSchemaHelper` を polymorphic 化し、 物理ファイルパスや raw JSON dict に加えて構造化 `Catalog`/`A2uiCatalog` モデルを直接受理・クロール可能に。 compiler/decompiler/prompt generator/`parse_express_response` へ伝播 (#1774)
- **eval: v0.9.1 の catalog スキーマ解決を修正**: `common_types.json` からの `catalog.json` 参照が `v0.9.1` 評価時に解決できなかった問題を、 `common_types_schema` の `$id` 相対で catalog スキーマを registry 登録することで修正 (#1789 解決, #1792)
- **v1.0 spec: Button サンプルを `child` に修正**: `specification/v1_0/docs/a2ui_protocol.md` の Button 例を正しい `child` プロパティに訂正 (#1790)
- **Python 最低要件を 3.10 へ引き下げ**: 全 SDK / eval / samples の `pyproject.toml` を `>=3.10` に緩和（従来より前方互換を拡大）。 併せて `tools/build_catalog/assemble_catalog.py` をリファクタ (#1808)
- **依存/ロックファイルを workspace 単一 `uv.lock` に統合**: 各パッケージ配下の個別 `uv.lock` を撤去しルートに集約、 パッケージ source を internal registry から PyPI へ切替、 CI を簡素化 (#1804)
- **リリース自動化スクリプトの統合**: `a2ui_agent/release.sh` を撤去し a2ui-core / a2ui-agent-sdk のリリース自動化を集約 (#1634)
- **CI/triage の整備 (雑務)**: needs-triage ラベリング (#1781)、 要対応 issue/PR の auto-flag ワークフロー追加 (#1801)、 triage ラベル二重付与の修正 (#1803)、 通知ノイズ削減のコメント削除 (#1805)

破壊的変更なし (Python 3.10 化・ロック統合はいずれも後方互換/ビルド内部変更)。

#### 2026-06-22〜27 新着 (web_core 0.10.3 / angular 0.10.2 / v1.0 spec reorg / Express compiler / Swift renderer)

- **web_core 0.10.3 / angular 0.10.2 リリース** (#1722): web_core に `setSignalImplementation`（signal 実装の差し替え）を追加、 angular を signal 変更へ整合
- **web_core signal swapping** (#1714): signal 実装をスワップ可能に
- **v1.0 validation サポート** (#1718): A2UI v1.0 の validation と nested reference path チェックに対応
- **streaming top-level objects 修正** (#1541): list wrap なしの top-level object streaming を修正
- **A2UI Express compiler / decompiler / parser 実装** (#1726、 robustness 修正 #1741): Express 形式の compiler 一式を実装
- **SDK 構造化 validation 診断** (#1738): structured validation details と統一 diagnostic taxonomy を導入
- **Swift renderer 初期コミット** (#1711): Swift renderer を新規追加
- **v1.0 spec reorg: pure A2UI protocol を A2A transport extension から分離** (#1725): `specification/v1_0/` を「純粋プロトコル」と「A2A transport 拡張」の境界で再編
- **spec docs split** (#1608): `renderer_guide.md` を `core_sdk_spec.md` / `framework_adapter_spec.md` / `sdks_spec.md` に分割（v0.9.1 / v1.0）
- **Express + v1.0 を eval suite へ統合** (#1740): Inspect-ai 評価スイートに Express と v1.0 を組み込み
- **angular testing utils を `@a2ui/angular/testing` で export** (#1737)
- **lit/vite8 対応**: shell sample が vite8 でコンパイルできるよう修正 (#1753)
- **MCP Apps demo (Angular) 復旧** (#1780): Angular 向け MCP Apps デモを復元

#### 2026-06-18 新着 (web_core 0.10.2 release / openUrl protocol 制限 / minimal catalog 整理)

- **web_core 0.10.2 リリース** (#1708): web_core パッケージを 0.10.2 へ
- **openUrl は http/https のみ許可** (#1707): `openUrl` が https/http プロトコルリンクのみを受け付けるよう制限（不正スキーム遮断、 セキュリティ）
- **minimal catalog を renderers から除去** (#1497): renderer 群から minimal catalog を削除して spec 側に残し、 simple basic samples を追加（refactor）
- **publish_npm.mjs を yarn 向けに調整** (#1703): CI の npm publish スクリプトを yarn 構成に合わせて修正

#### 2026-06-17 新着 (v1.0 strict catalog schema / Text heading variants 削除 BREAKING / 0.10.1 release prep)

- **spec(v1.0): Strict Catalog JSON Schema Restrictions and Consolidation** (#1629): catalog の JSON Schema 制約を厳格化し統合
- **BREAKING (v1.0): Text component の冗長 heading variants 削除** (#1668、 `spec(v1.0)!`): Text コンポーネントから重複する heading variant を除去（後方互換を破る spec 変更）
- **0.10.1 release prep**: 0.10.1 リリース準備の CI (#1679)、 recipes を community へ移動し 0.8 example を削除 (#1677)
- **angular: MarkdownRenderer を v0.8 public API に export** (#1658、 CHANGELOG entry #1670)
- **react: basic catalog integration tests 追加** (#1625)、 components 微調整 (#1624)
- **a2ui metadata が message 上にある旨を docs で明確化** (#1557)、 **lit: testing harness で a2ui messages を改変しない** (#1623)、 **lit: a2ui_explorer dev mode 修正** (#1666)
- **リンク全体修正 + CI/VSCode でのリンク検証セットアップ** (#1693)、 samples リスト拡充と contribution 呼びかけ (#1697)、 各 sample README 修正 (#1687, #1685, #1686, #1684, #1683)
- **docs**: Lynx を renderer roadmap に追加 (#1630)、 protocol version status labels の整合 (#1603)
- **1P 互換 transformations 適用** (#1655)、 **依存バンプ**: uv group (#1662)、 lodash-es 4.17.23 → 4.18.1 (#1665)、 pyjwt 2.12.1 → 2.13.0 (#1664)、 npm_and_yarn group 13 件 (#1654)

#### 2026-06-13 新着 (eval inference strategies)

- **eval に inference strategies 導入**: A2UI 評価フレームワークに inference strategies を導入 (#1602)

#### 2026-06-12 新着 (a2ui_core SDK 本格実装 / v0.10 → v1.0 spec 昇格)

- **v0.10 → v1.0 spec へ昇格**: 次期仕様ディレクトリが `specification/v0_10` 相当から `specification/v1_0` へ。 これに伴い v1.0 関連の更新が進行
- **BREAKING (v1.0): catalog instructions を inline Markdown 化 + `instructions.md` 廃止** (#1590): Catalog schema (`client_capabilities.json`) が相対 file URI ではなく plain Markdown 文字列を受け付けるよう変更、 外部 `instructions.md` を削除し catalog.json へ inline 化
- **a2ui_core SDK: reactive Signal / ComponentNode primitives 導入**: text-based layout renderer (テスト用) も追加 (#1579)
- **a2ui_core SDK: component state models / message processing / rendering 実装** (#1578)
- **a2ui_core SDK: components validation 付き catalog 実装** (#1577)
- **Python SDK Catalog アーキテクチャを Web Core parity へリファクタ** (#1612)
- **a2ui_agent を a2ui_core 依存へリファクタ** (#1582)、 **custom cuttable keys 設定サポート** (#1581)
- **core locale を decouple / deprecate**: catalog factory 経由で plumb するよう変更 (#1610)
- **Lynx ecosystem renderer 追加** (#1601)、 **AGenUI v0.9 renderer を ecosystem に追加** (#1450)
- **Samples 整理**: 一部削除し他を `samples/community` へ移動 (#1628)
- **AG-UI / CopilotKit の A2UI ガイダンス明確化** (#1619)
- **CI 刷新**: GitHub Actions を composite actions + 統合 CI workflow へリファクタ (#1621)、 a2ui_explorer に browser-based 統合テスト追加 (#1607)、 lint enforcement presubmit 追加 (#1600)、 Playwright screenshot regression を `test:visual` ターゲットへ移動 (#1635)
- **依存バンプ**: yarn パッケージ更新 (#1616)、 uv group を 9 ディレクトリで 12 更新 (#1593)
- **docsite の legacy/stable/candidate 参照を更新** (#1419)

#### 2026-06-09 新着 (a2ui_core SDK 立ち上げ / v0.10 spec 続報)

- **a2ui_core SDK 初期化**: schema 定義 + basic UI catalog components を持つ a2ui_core SDK を新設（Python 実装 / web_core の `basic_catalog` export、 CatalogInterface for v0.9）
- **BREAKING (v0.10): `theme` → `surfaceProperties` rename + `primaryColor` 削除** (#1525)
- **v0.10 spec: surfaceId は client session 毎にグローバル一意** (#1543)、 **Catalog schema に optional `instructions` field 追加 + rules.txt 廃止** (#1522)
- **spec: list templates 向け built-in `@index` function** (#1572)、 **catalog entity 命名規則を Unicode UAX #31 で規定** (#1573)
- **FunctionCall wire schema を refactor** し protocol specification と整合 (#1518)
- **monorepo を Yarn v4 workspaces へ移行** (#1054)

#### 2026-06 新着 (v0.10 spec initialState / MIME 規約変更 / Angular checks 型)

- **BREAKING: IANA MIME を `application/a2ui+json` に**: IANA 規約に合わせ mime type を `application/a2ui+json` へ変更 (POTENTIALLY BREAKING, #1493)
- **v0.10 CreateSurfaceMessage に optional `initialState`**: v0.10 で CreateSurfaceMessage に optional initialState を追加 (#1524)
- **Angular `checks` 型を ExtendedProps に露出**: ExtendedProps に checks 型を露出 (#1523)
- **migration notice 追加**: 移行告知を追加 (#1512)
- **GeneratedPluginRegistrant 除外**: 生成された GeneratedPluginRegistrant ファイルを ignore/削除 (#1530)

#### 2026-05 末 新着 (v0.10 spec / A2UI-over-MCP 強化 / Angular ComponentBinder)

- **Angular ComponentBinder children prop バグ修正**: v0.9 Angular ComponentBinder の children prop バグを修正、 unit test を real model 使用へ改善 (#1472)
- **v0.10 spec: Slider に `steps` property 追加**: v0.10 basic catalog の Slider に `steps` property を追加 (#1462)
- **basic_catalog.json refs クリーンアップ**: 残存する basic_catalog.json への参照を全削除 (#1463)
- **A2UI-over-MCP: static resources / dynamic tools サポート**: A2UI-over-MCP 統合で static resources と dynamic tools をサポート (#1471)
- **v0.9 / v0.10 catalog files 再構成**: v0.9 と v0.10 の catalog files を専用構造に再配置 (#1452)
- **web-core formatString 仕様準拠化**: formatString の objects/arrays を spec 通り JSON-stringify (#1430)
- **Angular dataModel computed property リファクタ**: dataModel computed property の redundant version() 呼び出しを削除 (#1475)
- **Angular explorer に v0.8 サポート**: Angular explorer app で v0.8 もサポート (#1436)

#### 2026-05 後半 新着 (v0.10 spec ドリフト + v0.9 streaming/MCP 整備)

- **v0.9 streaming parser suite**: v0.9 向けストリーミングパーサ一式を追加 (#1394)
- **v0.9 統合テスト整理**: 統合テストを `tests/v0_9` ディレクトリへ移動 (#1435)
- **v0.10 spec: Video `posterUrl` 削除**: v0.9 Angular から `posterUrl` 削除し v0.10 spec に追加 (#1373)
- **v0.10 spec: `placeholder` 同等処理**: 同等処理を v0.10 spec へ統合 (#1372)
- **v0.10 spec: Icon `color` prop 削除**: Icon コンポーネントから `color` prop を削除 (#1371, fix #1303)
- **A2UI×MCP サンプル復旧**: MCP 経由 A2UI サンプル動作復旧 + ガイド更新と図示 (#1076, #1439)
- **Icon snake_case 対応**: snake_case でも解釈できるよう Icon 内部修正 (#1433)

#### v0.9 後の変更点（web_core 0.9.2+ 含む、 2026-05 アクティビティ）

- **DataValueSchema recursion depth override**: v0_8 の `DataValueSchema` で recursion depth を override 可能に（refactor、 web_core） (#1431)
- **web_core locale サポート + pluralize 修正**: web_core に locale サポートを実装、 `pluralize` の挙動修正 (#1427)
- **Icon `color` prop 削除**: Icon コンポーネントから `color` prop を削除 (#1371, fix #1303)
- **CatalogComponentInstance を web_core へ移動**: 構造整理 (#1426)
- **A2UI ローカル uploader dashboard モダン化**: workspace_settings サンプル統合と dashboard の刷新 (#1381)
- **examples の動画リンクレジストリ**: 動画付き examples のレジストリを作成 (#1407)
- **AgentExtension パラメータ順序修正**: AgentExtension 作成時のパラメータ順序が逆になっていたバグ修正 (#1393)
- **Icon `path` → `svgPath` リネーム**: 型衝突解消のため Icon path プロパティをリネーム (#1347)
- **Accept/Reject CTAs / MCP tool allowlisting / モデル選択 / 依存リンク**: A2UI と editor app の多数の改善（モデル選択、 MCP tool allowlist、 dependency linking 等） (#1363)
- **Android / Jetpack Compose v0.9 renderer**: ecosystem ドキュメントに Android/Jetpack Compose v0.9 renderer 追加 (#1352)
- **Cloud Run デプロイ gcloud auth 前提条件**: Cloud Run デプロイガイドに gcloud authentication prerequisites 追加 (#1341)
- **React SVG CSS reset 除外**: SVG エレメントを React の CSS reset から除外 (#1252)
- **Angular CI ワークフロー最適化**: (#1357)
- **Python フォーマット強制**: 全 Python ファイルへフォーマット強制 (#1340)
- **Standard Catalog → Basic Catalog リネーム**: ドキュメントでの呼称統一と v0.9 ステータス更新 (#1302)
- **Vue3 renderer サポートドキュメント**: (#873)
- **A2UI Inspect AI 評価フレームワーク追加**: Inspect AI を用いた包括的 A2UI 評価フレームワーク導入（feat(eval)）
- **renderer publishing スクリプト改善**: CI 経由 renderer publishing スクリプトの整備 (#1317)
- **restaurant sample streaming duplicate surfaces 修正**: restaurant sample アプリの streaming で発生する duplicate surfaces エラー修正 (#1322)
- **C++ Agent SDK 完全削除**: 全 C++ ソース・ビルド設定を削除 (#1335)
- **Java Agent SDK 削除**: Java エージェント SDK 削除し Kotlin 実装にリファレンス (#1336)
- **Slider 動的 aria-label**: コンポーネントプロパティの null チェック追加と Slider の dynamic aria-label 化 (#1345)
- **prettier 自動インストール抑制**: フォーマット時に prettier インストール確認を求めない (#1342)
- **リポジトリ全体のフォーマット強制**: 全リポでの自動フォーマット適用 (#1338)
- **Kotlin 非決定テスト修正**: Kotlin の format check 追加と非決定テスト失敗の修正 (#1339)
- **Surface model `any` 削除**: surface model generic fallback から `any` 除去、Angular component host 更新 (#1314)
- **node プロパティ null check**: ランタイムエラー防止のための node プロパティ null チェック (#1334)
- **Catalog コンポーネント strict type**: 必須プロパティ実装を強制する strict type 追加 (#1320)
- **Checkbox value プロパティリネーム**: `checked` → `value` (#1332)
- **モジュール名衝突解消**: 明示的修飾名による module name collision の解消 (#1329)
- **Markdown-it npm 公開リリース**: markdown-it パッケージ初リリース (#1304)
- **markdown-it dompurify 3.3.1 pin**: 企業プロキシ環境向けインストール問題の解決 (#1313)
- **jsoncons による JSON Schema validation**: 堅牢な JSON schema validation のための jsoncons 統合 (#1274)
- **A2uiCatalog glob パターンサポート**: ファイルパスマッチングの glob パターンサポートと conformance test 有効化 (#1273)
- **Angular catalog コンポーネント props typing 改善**: (#1265)
- **Python unit test の conformance test 移行**: 残りの Python ユニットテストを conformance test 化 (#1266)
- **Kotlin unit test の conformance test 移行**: 残り Kotlin ユニットテストの移行 (#1301)
- **MCP samples ディレクトリ再編**: a2ui-in-mcpapps サンプルプロジェクト追加 (#1323)
- **AnyDuringSchemaAlignment alias 作成**: Angular `any` 問題追跡用 alias 追加 (#1310)
- **未テスト platform 削除**: テスト対象外プラットフォームの削除 (#1308)
- **URL hash navigation for Angular explorer**: Angular explorer の URL hash 移動実装 (#1269)
- **sandbox iframe origin/Vite module pathing 修正**: sandboxed iframe の origin と Vite module パス問題解決 (#1318)
- **Dart 飲食店 finder 追加**: Dart restaurant finder サンプル追加 (#1280)
- **Angular Types namespace 削除**: v0.8 renderer から Types namespace 削除 (#1292)
- **React typechecking 統合**: ビルドプロセスに型チェック統合 (#1284)
- **Kotlin SDK conformance tests 統合**: Kotlin SDK と A2UI コンフォーマンステスト統合 (#1129)
- **React shell v0.9 移行**: React シェルサンプルを A2UI v0.9 に移行 (#1262)
- **Dart SDK AI ワークフロー**: AI を用いた tests のワークフローと初期テスト定義 (#1251)
- **A2UI Examples ライブ JSON 編集**: メッセージ JSON のライブ編集サポート (#1243)
- **Angular primaryColor 伝搬**: basic catalog で primaryColor をコンポーネントに伝播 (#1242)
- **C++ ポート初期実装**: Python エージェント SDK の初期 C++ ポート (#1254)
- **License 修正コマンド追加**: ライセンス修正用 command/UI config 追加 (#1281)
- **MCP guides 整理**: (#1286)
- **web_core 0.9.2 リリース**: web_core パッケージ 0.9.2 リリース (#1212)
- **obscured enum type 追加**: v0_8 common types Zod に欠落していた `obscured` enum タイプを追加 (#1264)
- **private index URL CI 修正**: uv.lock の private index URL による CI 失敗修正 (#1261)
- **Gemini Enterprise Agent Engine 修正**: Cloud Run/Agent Engine へのデプロイ不可問題修正 (#1256)
- **try_activate_a2ui_extension 修正**: 拡張機能アクティベートのバグ修正 (#1234)
- **createSurface エラー仕様明確化**: 既存サーフェスに対する createSurface がエラーとなる旨を明確化 (#1238)
- **React widgets CSS variables スタイリング**: React レンダラーで CSS 変数を使ってウィジェットスタイル (#1205)
- **React weight プロパティ対応**: basic catalog で `weight` プロパティを honor (#1215)
- **Angular Tabs コンポーネント修正**: (#1218)
- **Angular restaurant サンプルスタイル合わせ**: (#1220)
- **Node.js / publishing スクリプト更新**: Angular テストを含む improve (#1177)
- **AG-UI ガイド追加**: feature quickstarts と AG-UI ガイド追加 (#1229)
- **Python google-adk 1.28.1 bump (セキュリティ)**: (#1219)
- **personalized_learning サンプル分割**: agent と client に分割 (#1244)
- **v0.9 レンダラーアイコンオーバーライド**: (#1146)
- **Angular Restaurant Sample v0.9 移植**: (#1189)
- **サーバーエラー伝播修正**: (#1203)
- **レンダラーパッケージ alpha.3 バージョンバンプ**: (#1178)
- **A2UI Theater**: インタラクティブ JSONL プレイバック＆ストリーミングビューア (#987)
- **A2A SSE ストリーミング**: (#1049)
- **concurrent surface サポート**: (#1037)
- **MCP Apps 統合**: (#748)

#### v0.9 の主要な変更点

- **Prompt First 設計**: 構造化出力優先からプロンプト埋め込み優先へ哲学変更
- **Web Renderers Data Model**: Web レンダラー向けデータモデルの完全実装 (#606)
- **メッセージタイプ刷新**:
    - `beginRendering` → `createSurface`
    - `surfaceUpdate` → `updateComponents`
    - 新規: `updateDataModel`, `deleteSurface`
- **コンポーネント構造簡素化**: キーベースラッパーからフラット構造へ
- **モジュラースキーマ**: `common_types.json`, `server_to_client.json`, `standard_catalog.json` に分割
- **Theme プロパティ**: `styles` → `theme` にリネーム
- **統一カタログ**: コンポーネントと関数を単一カタログに統合
- **Enum Case 標準化**: `lowerCamelCase` への統一 (#639)

#### 参考リンク

- [A2UI Specification](https://github.com/google/A2UI)

---

### ADP (Agent Data Protocol)

**現行バージョン**: v1.3.1 (2026-06)

**チェックアウト状態**: `v1.3.1-32-gf023035` (v1.3.1 + 32 commits、 HEAD 2026-07-05)

**管理**: CMU NeuLab

#### 2026-06-14〜2026-07-05 新着 (データセット拡充 + 整合性監査ツール)

- **新データセット追加**: OpenThoughts-Agent / Finch (#274)、 SWE-ZERO 12M (#258)、 enterpriselab (#271)
- **クロスデータセット整合性監査を追加** (#305)、 **サンプル fixture ドリフトチェッカーを追加** (#302)
- **LiteCoder のターミナル系プロンプト分離**: タスクからの分離 (#293) とヘルパー抽出 (#301)
- **役割正規化の修正**: AndroidControl (#286)、 Android in the Wild (#285)、 OmniAct 初期タスク順序 (#287)
- **OpenHands SDK の `<SOUL>` タグ system prompt ラッピングへ適応** (#272)、 native async condenser 生成 (#264)
- **プレースホルダ / 空 system メッセージの除去**: Toucan (#291)、 ORCA AgentInstruct (#290)、 OpenResearcher (#289)、 Nebius SWE-agent (#288)

#### 2026-06-13 新着 (ATIF 変換パイプライン)

- **ATIF conversion pipeline 追加**: Agent Trajectory Interchange Format (ATIF) への変換パイプラインを追加 (#256)

#### v1.2.0 / v1.3.0 / v1.3.1 リリース (2026-05〜06)

- **SFT データセット拡充**: LiteCoder Terminal SFT (#255)、 NVIDIA SWE-Zero OpenHands trajectories (#246)、 hybrid-gym trajectory (#248) を追加
- **OpenHands SDK condenser SFT**: openhands-sdk が condenser prompt SFT データを emit (#244)、 SDK-backed OpenHands SFT converter 追加 (#241)
- **condenser replay / identity**: in-memory event history で condenser replay (#252)、 condensation 不要時に identity trajectory を emit (#251)
- **Hugging Face chat-template 互換**: SFT サンプルを HF chat-template 互換に (#242)

#### v1.0.0 / v1.1.0 リリース (2026-05)

- **v1.1.0**: trajectory フィールドに「利用可能 API」を昇格させる正式化 (#212)
- **v1.0.0**: standardized schema versioning を導入 — スキーマバージョンを公式化、暗黙バージョンから明示バージョン必須化 (#211)
- **OpenHands browser tools optional**: 非Webデータセット向けに OpenHands ブラウザツールを任意化 (#213)

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| v1.0.0 へのジャンプ (schema versioning 明示必須) | 従来の暗黙 schema は明示バージョン宣言が必要 |

#### 最近の変更点 (1.x 前)

- **Catalog データセットガイドライン**: Catalog dataset ガイドライン追加と PR レビューワークフロー導入 (#186)
- **per-step reward フィールド追加**: Action / Observation スキーマに optional `reward: float | None` フィールド追加。RL トレーニングデータでの per-step reward 信号運搬対応。6 つの concrete action/observation type 全てに継承。デフォルト None で既存データセットへの影響なし (#183)
- **CoderForge-Preview データセット追加**: コーディング系トラジェクトリーデータセット (#167)
- **Nemotron Terminal Corpus データセット追加**: ターミナルコーパスデータセット (#165)
- **Toucan データセット追加**: (#163)
- **包括的ドキュメント追加**: 全サポート済みデータセット・エージェントの README/LICENSE と mini-coder インテグレーション完了 (#162)
- **SWE-Playground Trajectories データセット追加**: (#161)
- **Toucan-1.5M データセット実装**: (#154)
- **mini-coder トラジェクトリーデータセット**: (#155)
- **TextObservation `name` フィールド**: optional `name` フィールド追加 (#150)
- **MCP 統合 / SWE Agent コンバージョン整理**: MCP 追加、SWE Agent コンバージョン修正、エージェントコンバージョン整理 (#148)
- **SWE Agent std_to_sft 変換スクリプト**: (#140)
- **send_msg_to_user actions → MessageAction 変換**: (#145)
- **Nnetnav 修正＆Go-Browse フィルタ**: (#144)

#### 主要な変更点

- **データセットサポート**: SWE-Playground Trajectories, Toucan-1.5M, mini-coder trajectories, CoderForge-Preview, Nemotron Terminal Corpus, Toucan
- **MCP 統合**: エージェントツーリング連携
- **マルチエージェント対応**: OpenHands, SWE-agent, AgentLab
- **Pydantic 型安全性**: スキーマ検証強化

#### 参考リンク

- [ADP Protocol](https://github.com/neulab/agent-data-protocol)

---

### AG-UI (Agent-User Interaction Protocol)

**現行バージョン**: **TS SDK 0.0.57** / **@ag-ui/mastra@1.1.1 (新規リリース)** / **@ag-ui/a2ui-toolkit@0.0.4 (TS) + ag-ui-a2ui-toolkit@0.0.4 (Py)** / **@ag-ui/a2ui-middleware@0.0.10** / **@ag-ui/aws-strands@0.2.3 (TS) + ag_ui_strands@0.2.2 (Py)** / **ag_ui_adk@0.7.0 (Py)** / **@ag-ui/langgraph@0.0.42 (TS) + ag-ui-langgraph@0.0.42 (Py)** / **AG-UI .NET SDK (NuGet AGUI.\* 0.0.3)** / Python protocol 0.1.19

**チェックアウト状態**: `bc0a2c1d` (main、 HEAD 2026-07-17。 新規 `release/2026-07-15` タグ発行、 .NET SDK は `AGUI.Abstractions@0.0.4` 系へ前進)

#### 2026-07-18時点 新着 (release/2026-07-15 発行 + .NET SDK ドキュメント整備)

- **release/2026-07-15**: 新規リリースタグを発行
- **.NET SDK 整備**: dotnet reasoning text message-id 衝突修正 (#2200)、 .NET client/server verification とパッケージ parity notes の docs 追加 (#1971)
- **その他**: github actions 依存更新 (renovate)、 go-dojo を Go の既定 example 化 (#2047)。 破壊的変更なし

#### 2026-07-02〜2026-07-06 新着 (mastra 1.1.0/1.1.1 リリース + .NET NuGet リリース対応)

- **@ag-ui/mastra@1.1.0 / 1.1.1 リリース** (2026-07-02 / 07-03): 前窓までの Mastra interrupt/resume 整備を正式タグ化。 1.1.1 は fast-json-patch の default import 修正 (#2115) を含む
- **Mastra: Observational Memory を AG-UI アクティビティイベントとして表面化** (OSS-92)
- **Mastra: shared-state ストリーミングのリモートパリティ + 書き戻し**: `STATE_DELTA` 経由の共有ステート配信とクライアント編集同期 (OSS-414)
- **Mastra: `tracingOptions` パススルー公開と実行 traceId の表面化** (#2083)
- **dotnet: NuGet リリース対応**: AG-UI ワークフローへ NuGet リリースを追加、 sdk-dotnet AGUI.\* を 0.0.2 → 0.0.3 へ（パッケージのトリム・署名修正含む）
- **A2UI 連携デモ追加**: local+remote の A2UI デモと固定スキーマデモ
- **CI: Renovate 設定へ移行** (#1782, #1790)、 Java 用 GitHub Actions を削除 (#2090)
- **fix: missing-payload チャンクをストリーム中断せずスキップ** (#1635)

#### 2026-07-01 新着 (Mastra interrupt/resume 一斉整備 + .NET SDK パッケージ名訂正、いずれも未リリース)

> この窓 (`677dfca1` 2026-06-26 → `b91f32ea` 2026-07-01) に新規 package release タグは一つも切られていない。 下記は全て `main` 上の未リリース変更で、 各 package の現行バージョンは前回から不変。 中心テーマは Mastra 連携の割り込み(suspend/ask/resume)を LangGraph と挙動整合させる作業。

- **Mastra: native `useInterrupt` suspend/resume**: Mastra の `tool-call-suspended`→`on_interrupt` bridge 上に、 suspend→ask→resume の完全フロー(LangGraph と*挙動*整合、 payload 形状は非整合のまま)を実装。 resume が Mastra の suspend chunk が返す runId(`chunk.payload.runId ?? chunk.runId`)を round-trip するよう修正(AG-UI runId を使うと "No snapshot found" で失敗していた)。 dojo に local-only "interrupt" demo 追加 (#2040, OSS-88)
- **Mastra: 標準 interrupt-outcome を既定 ON 化 (破壊的変更)**: `emitInterruptOutcome` が既定 TRUE(opt-out)に。 構造化 `RUN_FINISHED.outcome` を割り込みの canonical signal とし、 標準 `RunAgentInput.resume` channel を消費。 snapshot runId を interrupt id へ `${runId}::${toolCallId}` で符号化。 **CopilotKit client >= 1.61.2 必須**(未満だと run が stranded)。 legacy の `on_interrupt` CUSTOM event は従来通り常時発火 (#2059, OSS-380)。 前段として opt-in の標準 RUN_FINISHED interrupt-outcome path を先行導入 (#2060, OSS-379)
- **Mastra: remote agent の resume-after-interrupt 対応**: `@mastra/client-js` 経由で suspend state + resume command を round-trip し「未対応」エラー経路を除去。 remote/local で on_interrupt payload と resumed-run event 列を同一化。 古い client-js(`resumeStream()` 非搭載)には明確な upgrade error で capability-guard (#2064, OSS-380)
- **Mastra: background task を AG-UI activity event 化**: `background-task-*` chunk を `ACTIVITY_SNAPSHOT` + `ACTIVITY_DELTA`(activityType `mastra-background-task`, taskId を messageId に round-trip)へマップ。 通常の tool render は抑制。 `@mastra/core >= 1.29` に bump、 dojo "Background Agents" demo(実 LLM)追加 (#2055, OSS-93)
- **Mastra: tool-call args の逐次ストリーミング**: 従来 tool call を buffer して単発 `TOOL_CALL_ARGS` で送出し generative UI が一括描画だった。 `tool-call-delta` を消費し個別の `TOOL_CALL_ARGS`(`TOOL_CALL_START`/`END` で括る)へ転送し progressive 描画に。 旧 `@mastra/core` 1.0.x は fallback で単発 flush (#2066, OSS-393)
- **Mastra: multi-turn での thread history 二重化を修正**: 複数ターン run で thread history が重複していたのを停止。 CopilotKit へ同期しつつ message identity を保持 (#2054, OSS-105 / #1556)
- **Mastra: `input.context` を tool へ確実に伝播**: resume 経路(local/remote)が `RequestContext` を verbatim 再利用し resumed run の新しい `input.context` を silently drop していた。 全経路を単一 `applyInputContext()` へ集約し `"ag-ui"` key 下に set(LangGraph の `state["ag-ui"].context` と idiom 等価) (#2065, OSS-392)
- **Mastra: CopilotKit 1.x runtime peer を許容** (#1730)
- **.NET SDK docs: hosting package を実名 `AGUI.Server` へ改名**: docs 上の `AGUI.Hosting.AspNetCore` を実際の publish 名 `AGUI.Server` に訂正(namespace / install コマンド / using / nav group)。 「framework 非依存の Microsoft.Extensions.AI adapter で Microsoft.AspNetCore.App に依存しない」と依存注記も修正。 あわせて .NET ロゴの hover CSS を suffix match 化 (`6f33b409`)
- **langgraph (test-only, 挙動変更なし)**: opt-in interrupt outcome + `resume[]` round-trip の test 追加、 stale comment 訂正(`copy`→`model_copy`) (#2053)。 既出の structured interrupt/resume の追試のみ
- **build/deps 雑多**: dojo build 修復のため hono を単一版へ pin、 `client-cli-example` の `@mastra/*` を bridge に合わせ 1.47 揃え、 remote resume 用に Mastra を最新へ bump (OSS-380)

#### 2026-06-26 新着 (AG-UI .NET SDK 新設 / langgraph structured interrupt/resume / ag_ui_adk 0.7.0 / aws-strands 0.2.3)

- **AG-UI .NET SDK 新規統合 (0.1.0-preview)** (#1963): C#/.NET 向けフル SDK を追加。 wire-format `AGUI.Abstractions`、 SSE `AGUI.Formatting`、 IChatClient ベースの `AGUI.Client` / `AGUI.Server`、 protobuf transport、 OpenTelemetry tracing、 dojo e2e、 TS-client ↔ C#-server クロス言語テストハーネスを同梱。 NuGet 0.1.0-preview 設定（リリースタグ未付与）
- **パッケージリリース群**: ag_ui_adk を 0.7.0、 @ag-ui/aws-strands (TS) を 0.2.3（0.2.2 経由）、 ag_ui_strands (Py) を 0.2.2 へ（release/2026-06-23・2026-06-24 でタグ付け）
- **langgraph: structured interrupt/resume サポート** (#1945、 issue #700): 構造化 interrupt/resume を追加（opt-in、 デフォルト off）。 `Interrupt.id` のため **`langgraph>=0.6.0` を必須化**
- **langgraph: DeepSeek `reasoning_content` 対応** (#1256): `additional_kwargs` 内の DeepSeek 形式 reasoning_content を処理
- **langgraph: stable messageId 再利用** (#1317): text→tool→text run 間で messageId を安定再利用（run でなく node スコープ）
- **langgraph: deprecation-warning cleanup** (#1215): `context_schema` / `get_config_jsonschema` の後方互換 fallback、 非 deprecated jsonschema API
- **langgraph 各種**: 同一 id content edit 検出 (#1748)、 `dump_json_safe` で非 string dict key (UUID) を処理 (#1741)、 `/health` path の trailing slash strip (#700)
- **aws-strands robustness**: halt 時 `RUN_FINISHED` 前に stranded tool call を drain、 空 content に非空 tool result を送出、 dynamic A2UI 完走のため強制 `render_a2ui` ターン、 a2ui_fixed_schema demo 追加 (#2021, #2023)
- **Agno 機能拡張** (#1895): AG-UI feature set を拡張し agno を `>=2.6.19` へ
- **A2UI integration skill (docs)** (#1993, #2043): AG-UI の A2UI integration skill を新設、 middleware API + catalog-forwarding 自動注入 DX に追従
- **RunAgentInput optional フィールド明確化** (#2028): client 提供の run tools / optional `run_agent_input` フィールドを明確化

#### 2026-06-20 新着 (langgraph/aws-strands/middleware リリース群 / ADK A2UI sub-agent rendering OSS-158 / agent resolver / strands HITL 修正)

- **パッケージリリース群**: @ag-ui/a2ui-middleware を 0.0.10、 @ag-ui/aws-strands (TS) + ag_ui_strands (Py) を 0.2.1、 @ag-ui/langgraph (TS) + ag-ui-langgraph (Py) を 0.0.42 へ bump（release/2026-06-19 でタグ付け）
- **ADK へ A2UI sub-agent rendering tool 移植 (OSS-158)**: recovery loop 付き A2UI sub-agent rendering tool 追加、 `generate_a2ui` tool の自動注入（Strands parity）、 intent="update" で先行 A2UI surface を再構成、 recovery 枯渇時に hard-failure envelope を surface、 fixed-schema A2UI dojo demo + Gemini-shaped aimock fixtures 同梱。 google-adk floor を 1.28.1 に宣言し `<3.0` を許可（`<2.0` cap を撤廃）
- **langgraph: progressive A2UI paint**: inner `render_a2ui` デルタを stream して段階描画（TS / Py 両方）、 native `OnChatModelStream` 経由で A2UI render を stream し custom-event relay を撤去、 shared `split_a2ui_schema_context` を使用、 ag-ui-a2ui-toolkit>=0.0.4 を必須化
- **aws-strands: A2UI catalog parity + streamed catalogId stamp** (TS / Py 両方)、 **strands HITL 修正**: resume 時に HITL tool result を破棄せず転送
- **a2ui-middleware: surfaceId 単位で final-envelope paint を dedup**
- **minimal ADK agent resolver 追加**: assistant message history から agent を解決、 tool result history routing の scope 化、 assistant message 上の adk author 保持、 tool-result resolver pinning の example 追加
- **adk-middleware CI**: google-adk 2.x test leg を allowed-to-fail (informational/green) として追加 (#1947)、 uv.lock を google-adk 1.x 最新へ re-resolve (#1946)

#### 2026-06-17 新着 (a2ui-toolkit 0.0.4 / a2ui-middleware 0.0.9 / schema-context split / license 整備)

- **a2ui-toolkit を 0.0.4 へ**: @ag-ui/a2ui-toolkit (TS) / ag-ui-a2ui-toolkit (Py) を 0.0.4 に bump（pyproject の toolkit version revert を経由）
- **a2ui-middleware を 0.0.9 へ**: @ag-ui/a2ui-middleware を 0.0.9 に bump
- **a2ui-toolkit: A2UI schema-context split + catalog resolver 追加 (TS / Py 両方)**: schema と context を分離し catalog resolver を導入
- **a2ui-middleware: frontend 登録の catalog id へ fallback**: catalog id 未解決時に frontend-registered catalog id へフォールバック
- **aws-strands 修正**: strands hello injection fallback (#1761)、 tool snapshot predicate の中央集約、 snapshot 無しの phantom tool-call parent 回避
- **dojo: chat e2e sends の安定化**
- **license 整備 (#1624)**: ag-ui-protocol Ruby gem に LICENSE 同梱、 @ag-ui/spring-ai を Apache-2.0、 @ag-ui/langchain を MIT / @ag-ui/mastra を Apache-2.0 に upstream 整合、 publish 対象パッケージの LICENSE + license-field カバレッジを完備、 adk/aws-strands pyproject の license-files を version の後に並べ替え

#### 2026-06-15 新着 (aws-strands 統合 0.2.0)

- **aws-strands 統合を 0.2.0 へ**: integration-aws-strands-ts (@ag-ui/aws-strands@0.2.0) と integration-aws-strands-py (ag_ui_strands@0.2.0) を 0.2.0 に bump（A2UI subagent アーキテクチャ移植に続くメジャーマイナー昇格）。 release/2026-06-15 でタグ付け

#### 2026-06-13 新着 (TS SDK 0.0.57 / aws-strands A2UI subagent / langgraph 修正群)

- **TS SDK 一式を 0.0.57 へ**: @ag-ui/core / client / encoder / proto / create-ag-ui-app を 0.0.57 に bump
- **aws-strands に A2UI subagent アーキテクチャ移植**: Python adapter と TypeScript adapter の両方へ A2UI subagent アーキテクチャを port。 CORS origin デフォルトを Python adapter に合わせ literal `"*"` に
- **client: HttpAgent の default fetch を bind**: ブラウザでの "Illegal invocation" を防ぐため HttpAgent で default fetch を bind
- **a2ui-toolkit: child-reference cycle 検出**: singular child を validate し child-reference cycle を検出 (deep child-chain cycle テストの de-flake、 child adjacency builders の ref-field scope ドキュメント化 #1948)
- **langgraph 修正群**: TOOL_CALL_RESULT で ToolMessage id (tool_call_id fallback 付き) を使用、 `prepare_regenerate_stream` で runtime config を保持 (#1749)、 runtime context を kwargs 経由で転送、 reasoning content をターン跨ぎで lossless に round-trip
- **dojo: CopilotKit 1.60.1 採用** (1.60.0 経由)、 langchain-core バージョン衝突のため langchain agent を無効化、 weather demo tools を test 下で決定的に
- **多数の修正 merge**: multi-LRO resume gating、 duplicate terminal event、 messages snapshot の reasoning dedup、 ADK session read cache、 LLMAgent HITL confirmation、 ADK LRO duplicate tool call、 client subscriber clone OOM、 SSE drop recovery regression test、 canary publish action、 proto license metadata

#### 2026-06-09 新着 (TS SDK 0.0.56 / A2UI toolkit)

- **TS SDK 一式を 0.0.56 へ**: @ag-ui/core / client / encoder / proto / create-ag-ui-app を 0.0.56 に bump
- **@ag-ui/a2ui-toolkit 0.0.3 を公開**: A2UI 連携 toolkit を publish し、 langgraph TS 統合（@ag-ui/langgraph@0.0.40）が利用。 A2UI dynamic schema params 修正も同梱
- **langgraph 統合 bump**: ag-ui-langgraph@0.0.41 (Py) / @ag-ui/langgraph@0.0.40 (TS)
- **adk-middleware**: live-test のデフォルトモデルを gemini-3.5-flash に更新

#### 2026-06 上旬 (TS SDK 0.0.55 / protocol 0.1.19 / mcp-middleware)

- **client run_id を RUN_FINISHED で保持**: RUN_FINISHED イベントで client の run_id を保持 (#1582)
- **integration-langgraph-ts 0.0.36**: langgraph TS 統合を 0.0.36 に bump
- **sdk-py protocol 0.1.19**: Python SDK protocol を 0.1.19 に bump
- **TS SDK パッケージ 0.0.55 一括リリース**: client / core / encoder / proto を 0.0.55 に
- **event reducer: tool result 順序修正**: tool result を対応する tool call の後に配置 (client)
- **langgraph TS createAgent inner graph export**: inner graph を export
- **@ag-ui/mcp-middleware 追加**: mcp-middleware リリーススコープを追加

#### release/2026-04-22 の主要な変更点

- **State Snapshot/Delta コンパクション**: run 単位で STATE_SNAPSHOT と STATE_DELTA イベントを単一の最終状態に圧縮、fast-json-patch (RFC 6902) によるデルタ適用 (#1535)
- **release-python タグ作成 idempotent 化**: 再試行時の release-python タグ作成を冪等に (#1548)
- **interrupt-aware ランライフサイクル草案拡張**: ドキュメント proposal 拡張 (#1555)
- **Python SDK 0.1.18**: SDK Python 0.1.18 リリース
- **AgentCapabilities Python SDK 追加**: Python SDK に AgentCapabilities タイプ追加 (#1307)
- **LangGraph orphan tool message 保持**: `langgraph_default_merge_state` で orphan tool message 修正保持 (#1494)
- **Strands template hooks 転送**: per-thread `StrandsAgentCore` に template hooks 転送 (#1561)
- **Mastra resourceId 転送**: working-memory sync の Memory 呼び出しで `resourceId` を毎回転送 (#1560)
- **LangGraph エンプティストリング/フォールバック多数修正**: `resolve_message_content`、`handle_reasoning_event`、`handle_node_change` 等 (langgraph 系)
- **LFS マイグレーション**: `test-image.png` を LFS トラッキングへ。pre-commit フックで生バイナリの LFS バイパス検出
- **Talk to Us フォーム**: ドキュメントサイドバーに「Talk to Us」フォーム追加 (#1554)
- **prepareRegenerateStream config 転送修正**: `assistantConfig` と forwarded config を正しくマージ (#1509)
- **Python wheel パーミッション修正リバート**: 壊れた wheel ビルド原因のリバート (#1508)

#### release/2026-04-15 の主要な変更点

- **AWS Strands パッケージバンプ**: AWS Strands パッケージバージョン更新 (#1531)
- **AWS Strands kwargs 転送修正**: シグネチャイントロスペクションによる per-thread エージェントへの全 template kwargs 転送 (#1529)
- **LangGraph パッケージバンプ**: LangGraph 統合パッケージバージョン更新 (#1530)
- **CVE-2026-25528 セキュリティ修正**: 依存関係バージョンバンプによるセキュリティ脆弱性修正 (#1527)
- **ツール連続実行時の状態ストリーミング修正**: ツールが連続実行される際に state がストリーミングされない問題修正 (#1526)
- **A2UI ミドルウェア v0.9 対応**: v0.9 インラインカタログスキーマフォーマット対応
- **ADK getCapabilities 実装**: ADKAgent に `getCapabilities()` と `/capabilities` エンドポイント追加 (#1475)
- **ADK Dependabot 脆弱性修正**: adk-middleware の critical/high 脆弱性修正 (#1517)
- **ADK セッション冗長スキャン排除**: 冗長なセッションスキャンの排除と古い tool-call クリーンアップ修正 (#1514, #1515, #1516)
- **マルチインスタンスセッションキャッシュ hydration**: マルチインスタンスキャッシュの修正 (#1484)
- **Kotlin Ktor 3.2.4 アップグレード**: Ktor 3.1.3 → 3.2.4 (#1520)
- **reasoning/thinking イベント**: multi-agent サポート、イベントスロットルミドルウェア (#1427)
- **BinaryInputContent 後方互換ミドルウェア**: レガシー BinaryInputContent 互換ミドルウェア追加 (#1422)
- **Strands.py v0.1.5**: Strands.py リリース

#### release/2026-03-28 の主要な変更点

- **リリース自動化**: リリース自動化パイプライン統合
- **ADK ミドルウェア O(1) 最適化**: ADK ミドルウェアのルックアップパフォーマンス改善

#### 以前の主要な変更点

- **Claude Agent SDK 統合**: Claude Agent SDK インテグレーション追加 (#916)
- **Langroid 統合**: Langroid フレームワーク統合と Dojo デモアプリ統合
- **Bedrock Converse API 互換性**: LangGraphAgent での Bedrock Converse API 互換性修正 (#1300)
- **Reasoning Spec**: 推論仕様追加 (#1050)
- **マルチモーダル仕様**: multimodal spec 追加 (#1084)
- **Ruby SDK**: フルプロトコル実装 (#865)
- **Dart SDK v0.1.0**: フルプロトコル実装
- **フレームワーク統合**: LangGraph, Mastra, CrewAI 対応
- **状態管理**: JSON Patch デルタ (RFC 6902) サポート

#### 参考リンク

- [AG-UI Protocol](https://github.com/ag-ui-protocol/ag-ui)

---

### AgentSkills

**現行バージョン**: 継続的デプロイ（バージョンタグなし）

**チェックアウト状態**: HEAD `38a2ff8` (2026-07-09、 タグ皆無)

**管理**: Anthropic

**2026-07-18時点**: spec 本体は今期変更なし。 early July 以降の commit は client showcase / docs 追加のみ (`docs/specification.mdx` の実質変更は 6月以前が最後)。 破壊的変更なし

#### 2026-07-01 新着 (ロゴアセット調整のみ)

- **正方形クライアントロゴのスケール調整** (#446): 画像アセットのみの変更。 仕様・コード変更なし

#### 2026-06-12〜2026-06-30 新着 (クライアントショーケース追加のみ)

- **Deep Code をクライアント一覧に追加**: `docs/snippets/clients.jsx` に Deep Code エントリと dark/light ロゴ SVG を追加。 spec には非接触 (#421)

前回記録 (5d4c1fd, 2026-05-21) から1ヶ月以上経っているが、 実際の upstream 活動はこの1件のみ。 spec/schema 変更なし、 バージョンタグも依然ゼロ。

#### 2026-05 後半 新着

- **name field 文字範囲修正 (digits 許可)**: spec の name field 文字範囲を alphanumeric + digits に修正 (#384)
- **bub クライアント追加**: bub をクライアント一覧に追加 (#340)
- **Superconductor クライアント追加**: Superconductor を ClientShowcase に追加 (#377)
- **Vita ロゴ追加**: Agent Skills logo carousel に Vita ロゴ追加 (#332)
- **Tabnine クライアント追加**: ClientShowcase に Tabnine 追加 (#349)
- **README.md コンテンツ拡充**: home.mdx の内容を README.md に取り込み、READMEのスタンドアロン化

#### 最近の変更点

- **ランディングページ刷新**: home.mdx に「What are Agent Skills?」「How do Agent Skills work?」セクション追加、Why/What セクション統合、Adoption 再構成
- **fast-agent クライアント追加**: fast-agent をクライアント一覧に追加、ロゴサイズ調整 (#327, #328)
- **Google AI Edge Gallery 追加**: Agent Skills クライアントリストに追加、ソースコード URL 追加
- **Workshop.ai クライアント追加**: (#314)
- **nanobot クライアント追加**: (#315)
- **LogoCarousel 簡素化**: 共通 `clients.jsx` 抽出とマージンオーバーライド
- **Get Started カード縮減**: home.mdx の "Get started" を Quickstart と Specification の 2 枚に縮約
- **Progressive disclosure リンク統合**: specification.mdx への統一
- **`what-are-skills.mdx` 削除**: 冗長なドキュメント削除
- **Client Showcase ページ**: Web ベースクライアントショーケースページ (#291)
- **シャッフル/アルファベット切替**: ClientShowcase にトグル追加

#### 主要な変更点

- **Discord リンク追加**: README とドキュメントに Discord リンク追加
- **Kiro ロゴ追加**: Kiro ロゴ追加
- **ランタイムバージョン例**: 互換性フィールドにランタイムバージョン例追加
- **クイックスタートガイド**: スキル作成者向けクイックスタートガイド追加
- **ベストプラクティスガイド**: スキル作成者向けベストプラクティスガイド追加 (#224)
- **Apache 2.0 ライセンス**: トップレベル LICENSE 追加 (#122)

#### 参考リンク

- [AgentSkills](https://agentskills.io)

---

### MCP (Model Context Protocol)

**現行バージョン**: 2025-11-25 (次期リリース候補 `2026-07-28-RC` 作業中)

**チェックアウト状態**: `2026-07-28-RC-243-g26897cc3` (2026-07-28-RC タグ後の draft 作業継続中、 HEAD 2026-07-15。 `schema/draft/schema.ts` の `LATEST_PROTOCOL_VERSION = "2026-07-28"`。 finalized tag 未発行 = **Release Candidate / draft 段階**)

#### 2026-07-18時点 新着 (2026-07-28-RC draft: stateless 化に向けた大型破壊的変更が landing)

**注意**: 以下は RC/draft 段階で未確定。 finalize されると MCP の接続モデルが根本的に変わる。

- **ステートレス化 (handshake 撤廃)**: `initialize`/`notifications/initialized` を廃止し、 全リクエストが `_meta` に protocol version と client capabilities を載せる。 版不一致は `UnsupportedProtocolVersionError` (SEP-2575)
- **session 廃止**: Streamable HTTP から `Mcp-Session-Id` を削除、 状態はサーバ発行 handle をツール引数で渡す (SEP-2567)
- **`server/discover` 追加**: サーバが対応版/capabilities/identity を広告する RPC を MUST 実装 (SEP-2575)
- **`subscriptions/listen` 導入**: HTTP GET と `resources/subscribe`/`unsubscribe` を単一 long-lived POST-response stream に置換 (SEP-2575)
- **MRTR パターン + `resultType`**: server 起点の `roots/list`/`sampling`/`elicitation` を廃し `InputRequiredResult` を返す方式へ。 全 result に必須 `resultType` (SEP-2322)
- **tasks を extension 分離** (`io.modelcontextprotocol/tasks`)、 `ping`/`logging/setLevel` 削除、 resource not-found error code `-32002`→`-32602`

| 破壊的変更 | 影響 |
|------|------|
| initialize handshake 撤廃・per-request メタ化 | client/server の接続確立フローを全面書き換え |
| session (`Mcp-Session-Id`) 廃止 | server-minted handle への移行が必要 |
| server-initiated request 廃止 → MRTR | sampling/elicitation/roots の実装が非互換 |
| `ping`/`logging/setLevel`/SSE resumability 削除 | 該当機能の呼び出しが不能に |

**注目**: この窓の SEP 活動は既 Final の **SEP-2243 (HTTP ヘッダ標準化)** の post-Final errata に集中し、 `Mcp-Param-*` ヘッダ発行ロジックの TTL 分離と base64 sentinel の大文字プレフィックス扱い反転という2件の規範的挙動修正が landing した。 in-flight の standards-track SEP 群 — SEP-2567 (Sessionless MCP) / SEP-2575 (Make MCP Stateless) / SEP-2596 (Feature Lifecycle/Deprecation) / SEP-2577 (Deprecate Roots/Sampling/Logging) / SEP-2106 (Tools schema JSON Schema 2020-12) / SEP-2164 (resource-not-found error code) / SEP-2468 (Issuer iss param) / SEP-2484 (Conformance Tests for Standards Track SEP) / SEP-2663 (Tasks Extension) — はいずれも draft のまま据え置きで、 この窓での status 遷移はなし。

**訂正**: 前回記録で「SEP-2243 (HTTP Standardization) 撤去 (#2914)」としていたが、 現時点の checkout (`docs/seps/2243-http-standardization.mdx`) では SEP-2243 の Status は **Final / Standards Track** であることを確認した。 前回記録時点の判断が誤りだったか、 SEP が withdrawal 後に再提出されて Final 化した可能性がある。 以降の記述は「SEP-2243 は Final」を正として扱う。

#### 2026-07-01〜2026-07-07 新着 (2026-07-28 リリース準備の広報 + 依存バンプのみ、 spec 実質変更なし)

- **2026-07-28 リリース向け SDK ベータ告知ブログを追加** (#2988、 記述の訂正 #2997): RC/リリース準備がドキュメント面で進行
- **Code of Conduct に異議申し立てチャネルを追加** (#2993)
- **workflows: slash-commands で Dependabot 自動承認を有効化** (#3018)
- **開発依存バンプ**: typedoc 0.28.20 (#3014) / typescript-eslint 8.62.1 (#3013) / prettier 3.9.4 (#3012) / tsx 4.23.0 (#3015)
- **注記**: `docs/specification/*/schema.mdx` に大きな差分が出るが typedoc バンプに伴う生成 HTML の再生成であり、 実質的な仕様変更ではない。 in-flight SEP 群の status 遷移もこの窓ではなし

#### 2026-06-30 新着 (SEP-2243 HTTP ヘッダ標準化 Final の errata / 微修正)

- **Mcp-Param-\* ヘッダ発行を schema TTL から分離**: `Mcp-Param-*` カスタムヘッダの client behavior を再定義。 旧文言「キャッシュした `inputSchema` が stale なら omit」は `ttlMs: 0` で無限ループ (常時 stale→常時 omit→server reject→tools/list 再取得→また stale) を起こしていた。 新文言では「最後に取得した `inputSchema` で構築、 一度も取得していない時のみ omit、 reject 時は refresh-and-retry (ヘッダ欠落・body 不一致の両方をカバー)」に変更。 TTL は tools/list の再取得ペース制御であってヘッダ発行の gate ではない、 と整理。 draft Streamable HTTP transport 仕様にも反映 (**規範的挙動変更**、 #2972)
- **base64 sentinel の大文字プレフィックス扱いを反転**: SEP-2243 conformance テーブルの矛盾を修正。 `=?BASE64?...?=` (大文字プレフィックス) は旧「Server MUST accept (case-insensitive prefix)」から「Server treats as literal value, not Base64」へ変更。 base64 sentinel プレフィックスは**小文字 `base64` のみ有効 (case-sensitive)** に確定 (**規範的挙動変更**、 #2937)
- **deprecated features テーブルの並び順修正**: `specification/draft/deprecated.mdx` を「最初に deprecated 化された spec バージョンの降順」に整列。 内容 (SEP-2596 / SEP-2577 / PR #2858 由来の deprecation 項目) は既出で行の並び替えのみ (368e013c)
- **依存 bump のみ (spec 影響なし)**: prettier 3.8.4→3.9.3 (#2987)、 eslint 10.5.0→10.6.0 (#2986)、 typescript-eslint 8.61.1→8.62.0 (#2985)

| 変更 | 種別 | 影響 |
|------|------|------|
| base64 sentinel 大文字プレフィックス → literal 扱い (#2937) | 規範的挙動変更 (Final errata) | 旧 case-insensitive 実装は非準拠に。 プレフィックスは小文字 `base64` のみ |
| Mcp-Param-* ヘッダ発行を TTL から分離 (#2972) | 規範的挙動変更 (draft) | `ttlMs: 0` での reject ループ解消。 client は最新 schema でヘッダ構築 |

#### 2026-06-25 新着 (subscriptions/listen response / security best practices / IG charter 群 / SEP-2243 撤去)

- **`subscriptions/listen` graceful end response** (#2953): 空の `SubscriptionsListenResult` を追加し、 サーバが subscription の正常終了（shutdown 等）を transport drop と区別して通知可能に。 `subscriptionId` を `_meta` で運搬、 schema/draft 再生成と stream-notification examples への subscriptionId backfill を同梱（additive optional のため非破壊）
- **listen stream の SSE keep-alive 推奨** (#2954): `streamable-http.mdx` / subscriptions pattern で listen stream に SSE コメント行 keep-alive を推奨
- **server/discover の version-selection 整理** (#2955)
- **Security best practices チュートリアル新設** (#1554): `tutorials/security/security_best_practices.mdx` + `docs/community/security.mdx` を追加
- **SECURITY.md 拡充** (#2973): SDK 脆弱性開示プロセスと stdio trust-boundary ガイダンスを追加
- **Enterprise Managed Authorization**: account-linking ガイダンスを完成、 壊れた spec リンクを修正 (#2945, #2960)
- **Financial Services Interest Group charter 新設** (#2979)、 **Primitive Grouping Interest Group charter 新設** (#2942)
- **AI contribution policy を `AI_POLICY.md` へ分離** (#2965)
- **Kotlin SDK を Tier 3 に** (#2513)、 Interceptors WG に Lead 追加
- **SEP-2243 (HTTP Standardization) 撤去** (#2914): 陳腐化した proposal doc を削除（wire protocol の破壊ではなく SEP の取り下げ）

#### 2026-06-20 新着 (error code allocation / client-matrix・extension support 拡充 / enterprise-managed auth docs)

- **error code allocation 整備** (#2907): JSON-RPC エラーコードの allocation を整理（fweinberger/error-code-allocation）
- **extension support matrix に Microsoft 365 Copilot 追加 + MCP Apps client list 更新** (#2637)
- **client-matrix 拡充**: PostHog Code を client-matrix に追加 (#2946)、 Archestra.AI を OAuth Client Credentials サポートとしてマーク (#2950)
- **enterprise-managed authorization docs**: stable な enterprise-managed authorization spec へのリンク更新 (#2949)、 enterprise-managed auth の blog 追加 (#2944)
- **build-rust-mcp-client doc 追加** (#2864): Rust MCP client のビルドドキュメント
- **依存バンプ**: npm_and_yarn group (#2957)。 spec 本文への影響なし

#### 2026-06-17 新着 (EMA / Security Interest Group charter / MRTR・elicitation draft 整備 / deps)

- **EMA Interest Group charter 追加**: EMA IG の charter を新設し prettier で整形、 Lead Maintainer sponsor 追記と facilitator 名修正、 Discord channel / invite link を併記
- **Security IG charter 追加 + charter 再配置**: Security Interest Group charter を追加し、 全 charter を `working-groups/` と `interest-groups/` 配下へ移動
- **MRTR (Multi-Round Tool Result) draft 整備**: required `resultType` と SSE resumability removal の changelog entry 追加、 caching 要件を complete results に限定しキャッシュキーを定義、 transport 固有 cancellation 向けに request timeout guidance を復元、 server / client feature ページを `_meta` / resultType / per-request capabilities に整合
- **elicitation 系 draft クリーンアップ**: URL mode elicitation request から `elicitationId` を削除、 `notifications/elicitation/complete` を draft から削除、 `elicitationComplete` を `subscriptions/listen` filter に追加、 core client notifications が Streamable HTTP 上では発生しない旨を明確化
- **subscriptionId 仕様**: subscriptionId が JSON-RPC ID を string / number で verbatim に運ぶよう定義、 説明を request ID のみへ簡素化
- **x-mcp-header 整備**: x-mcp-header rule の重複排除、 statically reachable properties へ制限、 Base64 sentinel encoding を `Mcp-Name` header にも拡張
- **discover.mdx**: Response Fields テーブルを Data Types セクションへ置換
- **依存バンプ**: esbuild (#2911, #2910)、 eslint 10.4.1 → 10.5.0 (#2916)、 typescript-eslint 8.60.1 → 8.61.0 (#2917)、 prettier 3.8.3 → 3.8.4、 markdown-it。 spec 本文への影響なし

#### 2026-06-13 新着 (依存バンプのみ)

- **esbuild バンプ**: deps / deps-dev の esbuild をバンプ (#2911, #2910)。 spec 本文への変更はなし

#### 2026-06 新着 (message patterns 再編 / stdio legacy-fallback / Server Card WG)

- **Authorization spec ドキュメント再構成**: AS discovery を独立ドキュメントに分離し、 client registration を1ページに統合（normative 文言をテーブルから本文へ昇格、 2026-06-04〜05 の localden/auth-spec 一連）
- **schema 修正: `ElicitationCompleteNotificationParams`** を NotificationParams 継承として抽出 (#2866)
- **Registry / Server Card / Triggers & Events charter に repository links 追加** (#2887)

- **message patterns ページ再編**: utilities/ から message patterns ページを移動・再編し、 リンクを更新
- **stdio legacy-fallback ルール修正 + 互換性マトリクス**: stdio の legacy-fallback ルールを修正し、 compatibility matrix を追加 (#2844)
- **draft spec overview 整理**: deprecated features を削除し、 extensions セクションを追加
- **Server Identity WG → Server Card WG リネーム**: WG を改称、 Sam Morrow を IG/WG に追加 (#2827)
- **build(deps) 群**: vitest / typescript-eslint / tsx / eslint / actions 各種を bump

#### 2025-06-18 → 2025-11-25 で導入された主要 SEP (新着補完)

- **SEP-973 Icons metadata**: tools/resources/prompts にアイコンを公開する metadata
- **SEP-835 Incremental scope consent**: `WWW-Authenticate` 経由の段階的スコープ同意
- **SEP-1036 URL mode elicitation**: `ElicitResult` / `EnumSchema` 標準化、URL mode elicitation
- **SEP-1330 titled / multi-select enum elicitation**: enum の titled / multi-select 化
- **SEP-1577 Sampling に tool calling**: `tools` / `toolChoice` を sampling に追加
- **SEP-1686 Tasks (実験的)**: 永続的リクエストの polling / deferred result 取得
- **SEP-991 OAuth Client ID Metadata Documents**: 推奨 client 登録メカニズムとして追加 (PR #1296)
- **SEP-1613 JSON Schema 2020-12 をデフォルト方言に**: schema dialect を明示固定
- **OpenID Connect Discovery 1.0 対応**: 認可サーバ発見を OIDC Discovery 準拠に拡張 (PR #797)

#### 2025-11-25 リリースの破壊的変更

| 変更 | 影響 |
|------|------|
| HTTP 403 for invalid Origin (PR #1439) | Streamable HTTP transport で不正 Origin に 403 必須化 — クライアント挙動に影響 |
| OAuth Protected Resource Metadata の RFC 9728 整合 (SEP-985) | `WWW-Authenticate` ヘッダ optional、`.well-known` への fallback — 既存実装の挙動見直し |
| 入力検証エラーは Tool Execution Error として返す (SEP-1303) | Protocol Error ではなく Tool Execution Error 方針に変更 |

#### 2025-11-25 後の変更点（次回リリース向けドラフト）

- **SEP-2575 unsupported protocol error code 追加**: SEP-2575 stateless MCP に対応するため、 unsupported protocol error のカスタムエラーコードを導入
- **SEP-2596: Specification Feature Lifecycle and Deprecation Policy**: 仕様の機能ライフサイクルと deprecation policy を明文化 (#2596)
- **SEP-2577: Roots / Sampling / Logging を deprecate**: 三機能の deprecation を進行 (#2577)
- **SEP-2106: Tools `inputSchema`/`outputSchema` を JSON Schema 2020-12 準拠化**: tools の schema を JSON Schema 2020-12 dialect に統一 (#2106)
- **SEP-2164: resource not found error code 標準化**: error code を -32602 で標準化 (#2164)
- **SEP-2468: MCP Auth Response で Issuer (iss) param 推奨化**: auth response に iss を推奨 (#2468)
- **SEP-2484: Standards Track SEPs は Final 到達に Conformance Tests 必須**: standards track SEP の Final 昇格に conformance tests を必須化 (#2484)
- **SEP-2663: Tasks Extension**: tasks extension SEP の Final 昇格と reformat (#2663)
- **SEP-2260 Final 昇格**: SEP-2260 を Final マーク
- **MRTR (Multi-Round Tool Result) スキーマ bugfix 群**: resultType 必須化の明確化と absent-field を後方互換として再フレーム、 notifications/message が request-scoped であることの明確化、 HTTP 後方互換 fallback の 400/404 body 検査による曖昧化解消
- **GitHub Copilot CLI / CIMD クライアント追加**: ChatGPT MCP Client support list に CIMD を、 clients list に GitHub Copilot CLI を追加 (#2741、d1b92de)
- **SEP-2575: Make MCP Stateless**: MCP をステートレス化する提案、 SEP-2567 の補完 (init removal) として位置付け (#2575)
- **SEP-2567: Sessionless MCP via Explicit State Handles**: explicit state handle 経由で sessionless MCP を実現する提案。 Final / Accepted ステータスに昇格、 spec language を draft に適用済み。 stdio SHOULD NOT、 list endpoints が request authorization で変化することを clarify、 connect_database example と Future Work を追加
- **SEP-2567 ↔ SEP-2575 関係再定義**: SEP-2567 を SEP-2575 の opt-in predecessor ではなく complementary (init removal) として再フレーム
- **MRTR スキーマ整備**: `IncompleteResult` を `InputRequiredResult` に rename、Multi-Round Tool Result の draft/schema.mdx 修正
- **Augmented Tool Call 拡張**: tasks augmented tool call フローのドキュメント更新
- **elicitation/roots ダイアグラム更新**: elicitation diagrams と roots ページのリフレッシュ
- **`requestState` 仕様改訂**: requestState ハンドリング要件のアップデート
- **`URLElicitationRequired` エラー削除**: URL Elicitation 自体は MRTR 経由で継続サポート、エラーは廃止
- **SEP リジェネレート**: prettier 適用 + SEP 再生成
- **Core Maintainer Emeritus 移行**: Che Liu, Basil Hosmer を Core Maintainer Emeritus へ移動
- **SDK Working Group チャーター**: SDK WG charter 追加 (#2662)、 work items を spec implementation と tiering に整理
- **`#general-sdk-dev` Discord チャンネル化**: SDK WG 用 Discord チャンネル指定
- **vm2 3.11.3 セキュリティバンプ**: GHSA-vwrp-x96c-mhwq 対応 (#2711)
- **TypeScript 6.0.3 / eslint 10.3.0 / typescript-eslint 8.59.1-8.59.3**: 依存バンプ群 (#2610, #2676, #2677)
- **typescript-json-schema 0.67.1 pin**: 0.67.2 → 0.67.1 への revert pin (#2714)
- **fast-uri 3.1.2**: dev deps の fast-uri バンプ (#2715)
- **Ruby client 明示的 connect サンプル**: Ruby client サンプルを明示的な connect 化 (#2685)

#### 2025-11-25 の主要な変更点

- **Interceptors WG チャーター**: Interceptors Working Group チャーター策定 (#2619)
- **MCP クライアントベストプラクティス**: docs に MCP クライアントベストプラクティス追加 (#2582)
- **Runbear クライアント追加**: Example Clients に Runbear 追加 (#2572)
- **`.well-known/agent-skills/` 発見エンドポイント**: MCP skills を `.well-known/agent-skills/` 経由で公開
- **Mintlify ディレクトリシンボリックリンク対応**: draft-sep / search-mcp-github skill の Mintlify インデックス修正 (#2597, #2604)
- **single Core Maintainer 承認明確化**: WG charter PR の single Core Maintainer 承認明確化 (#2592)
- **fork-based contribution first-class**: フォークベースコントリビューションをファーストクラスパスに
- **TypeScript 6.0.3**: TypeScript 6.0.2 → 6.0.3 (#2610)
- **HTTP Standardization (SEP-2243)**: HTTP トランスポートの標準化マージ
- **Deterministic tools/list ordering**: ツールリストの決定的順序仕様追加
- **Tool-name disambiguation**: ツール名の曖昧さ排除の明確化
- **Skills Over MCP IG**: Skills Over MCP Interest Group チャーター策定
- **Inspector V2 WG**: Inspector V2 ワーキンググループチャーター策定
- **mcpc CLI クライアント更新**: (#2576)
- **SEP-2207 OIDC リフレッシュトークンガイダンス**: (#2207)
- **Ruby SDK ドキュメント**: build-client ドキュメントに Ruby SDK サンプル追加 (#2486)
- **SEP-2350 クライアントサイドスコープ蓄積**: (#2350)
- **TypeScript 6.0.2**: TypeScript 5.9.3 → 6.0.2 (#2503)

#### 主要な変更点

- **Extensions トップレベルタブ**: Extensions を専用ページ付きトップレベルタブに昇格 (#2263)
- **SDK 階層評価**: Python SDK Tier 1, C# SDK Tier 1, Go SDK Tier 1, Java SDK Tier 2, Swift SDK Tier 3, PHP SDK Tier 3
- **OIDC / エンタープライズ管理認可**: OIDC とエンタープライズ管理認可の更新
- **実験的タスク機能**: アプリケーション駆動タスクアーキテクチャ、ポーリング付き状態追跡
- **Extensions フレームワーク** (SEP-2133, Final): 拡張機能ケイパビリティのスキーマ追加
- **MCP Apps サポート拡大**: Claude Desktop, ChatGPT, MCPJam, Postman, VSCode, goose, Copilot

#### 参考リンク

- [MCP Specification](https://spec.modelcontextprotocol.io/)

---

### MCP-Apps

**現行バージョン**: **v1.7.4 (2026-06-04)**

**チェックアウト状態**: `v1.7.4-7-g2ca6a59d` (v1.7.4 + 7 commits、 HEAD 2026-07-17)

#### 2026-07-18時点 新着 (draft spec 補完、 SDK は v1.7.4 のまま)

- **spec 追加 (未リリース)**: 欠落していた `HostCapabilities` フィールド追加 (#653)、 spec の `object-src` を `default-src` と同期 (#715)
- **注記**: npm SDK 版 (1.7.x) と spec 版 (`RELEASES.md` 0.3.0) を別体系で versioning。 tag 追跡対象は SDK 版 (v1.7.4 が最新)

#### 2026-07-07 新着 (draft spec: HostCapabilities フィールド補完)

- **spec: 欠落していた HostCapabilities フィールドを追加** (#653): `specification/draft/apps.mdx` を更新（フィールド追加のみで破壊的変更なし）。 この窓で唯一の仕様変更
- **docs: サポートクライアント一覧に mcp-use inspector バッジを追加** (#650)
- **docs: ext-apps/server の API Docs リンクを追加** (#697)

#### v1.7.4 後の変更点 (docs のみ)

- **map-server readme / code of conduct リンク修正** (#657): docs のリンク切れを修正。 spec / 実装への変更なし

#### v1.7.4 の主要な変更点（2026-06-04）

- **SECURITY: lazy-auth-server token exchange で PKCE 必須化 + redirect_uri バインド** (#681)
- **lazy-auth-server の base path 配下マウント対応**: base path 配下へのマウントをサポート (#683)
- **ext-apps 1.7.4 bump** (#685)

#### v1.7.3 の主要な変更点

- **lazy-auth-server example 追加**: lazy 認証サーバの example を追加 (#679)
- **ext-apps 1.7.3 bump**: ext-apps を 1.7.3 に bump (#680)

#### v1.7.2 の主要な変更点

- **example transitives パッチ群 bump**: example 配下の transitive 依存を最新パッチへバンプ (#658)
- **pdf-lib → @cantoo/pdf-lib フォーク切替**: pdf-server で maintained な `@cantoo/pdf-lib` fork へスイッチ（メンテナンス放棄対応） (#651)

#### v1.7.1 の主要な変更点

- **PDF Server lazy フォーム抽出**: range transport によるレイジーフォーム抽出と incremental viewer scans (#639)
- **PDF Server キャッシュ共有**: サーバーインスタンス間でのキャッシュ共有とフォームパースの dedupe (#637)
- **qr-server FastMCP host/port サポート**: Docker 互換性のための host/port 渡し (#372)
- **PostMessageTransport source 検証**: PostMessageTransport の source 検証ユニットテスト追加 (#536)
- **buildAllowAttribute ユニットテスト**: (#541)
- **CONTRIBUTING.md ガイド更新**: package preview のコントリビューティングガイド更新 (#601)

#### v1.7.0 の主要な変更点

- **ツール登録仕様 (WebMCP-style)**: Host から呼び出される Apps のツール登録を仕様追加 (#72)
- **MCP app sampling サポート**: stock SDK types 経由の MCP app sampling 対応 (#530)
- **Zod jitless デフォルト化**: Zod を jitless デフォルトに、`allowUnsafeEval` opt-out 追加（CSP strict 環境対応） (#618)
- **pre-handshake guard 統一**: `console.warn` に統一し、handshake 前のリクエストをガード (#620, #630)
- **one-shot handler 登録警告**: `connect()` 後の one-shot handler 登録時に警告 (#629)
- **React StrictMode クリーンアップ**: StrictMode での cleanup と late-handler guard の再登録緩和 (#631)
- **React autoResize 転送**: `useApp` から `App` へ `autoResize` を転送 (#622)
- **types 強化**: `McpUiToolMeta` での csp/permissions を never で禁止 (#624)、stale resourceUri JSDoc 削除 (#626)
- **依存関係パッチバージョンバンプ**: vite, hono, @hono/node-server のパッチバージョンへのバンプ (#616)

#### v1.6.0 の主要な変更点

- **Progress-based timeout reset**: `callServerTool` でプログレスベースのタイムアウトリセット対応 (#600)
- **E2E テスト堅牢化**: 初期 shrink-to-fit ズームのポーリングによるテスト安定化 (#607)

#### v1.5.0 の主要な変更点

- **PDF Server アノテーションラスタライズ**: インポート済みアノテーションのラスタライズ (#593)
- **PDF Server フォームフィールド保存堅牢化**: フォームフィールド save のロバスト性向上 (#591)
- **PDF Server ハイライト/下線/取り消し線インポート**: 既存 PDF からのインポート対応 (#592)
- **PDF Server `get_viewer_state`**: interact アクションに `get_viewer_state` 追加 (#590)
- **PDF Server ズームアウト改善**: fit 以下へのズームアウト許可 (#589)
- **PDF Server フルスクリーン・ピンチズーム**: フルスクリーン時の fit-to-page とピンチズーム (#583)

#### v1.4.0 の主要な変更点

- **PDF Server `save_as` アクション**: interact アクションに `save_as` 追加 (#580)
- **path-to-regexp ReDoS CVE 修正**: v8.3.0 → v8.4.1 (#576)
- **addEventListener/removeEventListener**: DOM モデル `on*` セマンティクス追加 (#573)

#### 参考リンク

- [MCP-Apps](https://github.com/modelcontextprotocol/ext-apps)

---

### MCP-UI

**現行バージョン**: `@mcp-ui/client` v7.1.1 (2026-05) / `@mcp-ui/server` v6.1.0 (2026-02)

**チェックアウト状態**: `client/v7.1.1-2-g2b10490` (v7.1.1 + 2 commits、 HEAD 2026-07-08。 repo は `MCP-UI-Org/mcp-ui` へ移行済み、 per-package tag `client/v*`・`server/v*` が現行スキーム。 root `CHANGELOG.md` は旧 `idosal/mcp-ui` 由来で stale=参照しない)

**2026-07-18時点**: v7.1.1 後の未リリース分として `require('@mcp-ui/client')` が exports を出すよう CJS ビルドを emit (#211)。 破壊的変更なし

#### v7.1.1 の主要な変更点

- **sandbox proxy iframe timeout cancel**: effect cleanup 時に sandbox proxy iframe timeout をキャンセル、 StrictMode での unhandled rejection を防止 (#190)

#### v7.1.0 の主要な変更点

- **`hostInfo`/`hostCapabilities` props**: `AppRenderer` に `hostInfo` と `hostCapabilities` props 追加 (#179)

#### v7.0.0 の主要な変更点

- **レガシー仕様削除**: レガシー仕様の完全削除（**破壊的変更**） (#185)
- **major bump 修正**: semantic release で前回 commit が major bump 失敗していたため修正 (#187)

#### 破壊的変更

| バージョン | 変更 |
|-----------|------|
| v7.0.0 | レガシー仕様の完全削除 |
| v6.0.0 | 廃止コンテンツタイプ削除、MIMEタイプ変更 |
| v5.0.0 | `delivery` → `encoding`、`flavor` → `framework` |

#### 参考リンク

- [MCP-UI](https://github.com/MCP-UI-Org/mcp-ui)

---

### NLIP (Natural Language Interaction Protocol)

**現行バージョン**: 1st edition (Ecma 承認 2025-12-10)

**管理**: Ecma TC56 NLIP（Ecma International）

**注目**: AI エージェント間および人間 ↔ AI エージェント間の **アプリケーション層通信プロトコル** の業界標準。 2025-12-10 に Ecma International が正式承認、 2026-01-25 に ISO へ提出済み。 Claude Skills 互換 reference 実装が 2026-02-28 公開予定（reference 実装側）。

#### 1st edition 構成（全 6 文書）

| 標準 | タイトル | 役割 |
|------|---------|------|
| **ECMA-430** | Natural Language Interaction Protocol (NLIP), 1st edition | プロトコル本体仕様（agent-to-agent / human-to-agent application-level） |
| **ECMA-431** | NLIP over HTTP/HTTPS binding | HTTP/HTTPS バインディング |
| **ECMA-432** | NLIP over WebSocket binding | WebSocket バインディング（CBOR + UTF-8 JSON フォールバック、 RFC 8949） |
| **ECMA-433** | NLIP over AMQP binding | AMQP バインディング |
| **ECMA-434** | Security profiles for NLIP | Agent Security Profiles（NLIP 適合実装に対する mandatory 要件） |
| **ECMA TR/113** | Explanatory guide to NLIP | informative な解説書（design philosophy / use-cases / sample exchange） |

#### リポジトリ構成（追跡対象）

- **`nlip-project/nlip_spec`**: Ecma 承認版 1st edition の README index（本サブモジュール）
- **`nlip-project/ecma_draft` / `ecma_draft1`**: First Draft 期のフィードバック収集リポ（履歴的）
- **`nlip-project/documents`**: TC-56 NLIP 関連ドキュメント
- **`nlip-project/security_guidelines`**: ECMA-434 のコンパニオン
- **`nlip-project/nlip_spec_swarm` / `nlip_web` / `nlip_agents` / `kivy-chat-mach2`**: 参照実装系

#### 主要な特徴

- **マルチトランスポート対応**: HTTP/HTTPS / WebSocket / AMQP の 3 系統バインディング（用途に応じて選択可能）
- **WebSocket × CBOR**: マルチモーダル通信のためのコンパクト・効率的バイナリエンコーディング、 JSON フォールバックも保証
- **Security Profiles 標準化**: NLIP 適合を主張する実装には ECMA-434 への準拠が **mandatory**
- **Royalty-free open source 標準**: Ecma International ガバナンスのもと royalty-free
- **A2A / MCP との位置関係**: A2A は agent ↔ agent の opaque 通信、MCP は agent ↔ tool/data の通信。 NLIP は **agent ↔ agent / human ↔ agent の natural-language application-level** 通信を担当する補完的位置

#### 参考リンク

- [nlip_spec (GitHub)](https://github.com/nlip-project/nlip_spec)
- [NLIP Project site](https://nlip-project.org/)
- [Ecma International - ECMA-430](https://ecma-international.org/publications-and-standards/standards/ecma-430/)
- [Ecma International - ECMA-431 (HTTP)](https://ecma-international.org/publications-and-standards/standards/ecma-431/)
- [Ecma International - ECMA-432 (WebSocket)](https://ecma-international.org/publications-and-standards/standards/ecma-432/)
- [Ecma International - ECMA-433 (AMQP)](https://ecma-international.org/publications-and-standards/standards/ecma-433/)

---

### OpenResponses

**現行バージョン**: タグなし (spec は日付版、 CHANGELOG 最新 = `2026-04-24`)

**チェックアウト状態**: `92c12d9` (remote HEAD detached、 HEAD 2026-07-15)

#### 2026-07-18時点 新着 (WebSocket transport + Response compaction + spec versioning)

- **WebSocket transport**: `/v1/responses` に WebSocket モードを追加。 `response.create` でターン開始、 HTTP streaming と同じ semantic event を再利用。 逐次ターン・`previous_response_id` 継続・60分接続上限・切断復旧を定義 (#71/#72)
- **Response compaction**: `POST /v1/responses/compact` エンドポイントと request/response schema を追加 (#68)
- **Spec versioning 導入**: specification/reference を日付版でバージョニングし `llms.txt` を追加 (#77, 2026-07-06)
- **assistant-message `phase` フィールド** (`commentary`/`final_answer`) 追加、 `logprobs` を任意化 (#45)
- 破壊的: `createResponse` operation ID を修正 — OpenAPI 生成 client の operation 名が変わる (要再生成)

#### 最近の変更点

- **Response phase コンパクション**: assistant message phase パラメータをソーススキーマに追加。phase スキーマと compaction スキーマを整合化、コンプライアンステストでカバー、neutral モデル説明導入 (#68)
- **compact response エンドポイント**: 仕様に compact response エンドポイント追加。compaction エンドポイントのドキュメント化 (#68)
- **WebSocket モードサポート**: OpenResponses に WebSocket モード実装（新規の大きな機能） (#71)
- **WebSocket 復旧コンプライアンスカバレッジ**: WebSocket recovery compliance テスト追加
- **WebSocket モードドキュメント整備**: WebSocket モードのドキュメントとバリデーション整合化
- **mise version bump**: `mise-bun` 環境のバージョン bump (#72)
- **composed schema fields レンダリング**: リファレンスドキュメントで composed schema fields をレンダー
- **AWS パートナー追加**: AWS パートナーロゴ追加 (#67)
- **Red Hat コミュニティ追加**: Red Hat ロゴ追加
- **コアメンテナーリスト更新**: メンテナー管理改善

#### 主要な変更点

- **Llama Stack 統合**: Llama Stack インテグレーション追加 (#29)
- **Databricks コミュニティ追加**: コミュニティセクションにロゴ追加
- **logprobs オプション化**: logprobs をオプショナルに変更 (#45)
- **CLI コンプライアンステスト**: `bin/compliance-test.ts` 追加
- **Bun 移行**: Node から Bun へパッケージマネージャー変更

#### 参考リンク

- [OpenResponses](https://github.com/openresponses/openresponses)

---

### UTCP (Universal Tool Calling Protocol)

**現行バージョン**: v1.1（仕様、 タグなし latest 追従、 直近 spec commit 2026-05-18）

**チェックアウト状態**: `5edfb3d` (remote HEAD detached、 HEAD 2026-07-17。 HEAD 付近は毎日の `chore: update contributors data` 自動 commit のみで、 spec 実体の変更は 2026-06-24 以降なし)

**管理**: Universal Tool Calling Protocol コミュニティ（独立 OSS）

**2026-07-18時点**: 実体変更なし。 現行 spec は **v1.1** (secure-by-default: 全 call template に `allowed_communication_protocols` を追加、 未指定時は同一 protocol の tool のみ登録・呼出し可)。 破壊的変更なし

**注目**: MCP の **構造的代替案 / 補完案**。 MCP が「proxy 経由でツール呼び出し」する一方、 UTCP は **agent が discovery 後に native endpoint (HTTP/gRPC/WebSocket/CLI) を直接叩く**設計で、 wrapper tax + latency を排除し、 既存の auth/billing/security をそのまま活かせる。 v1.0 で plugin-based 構成へ全面再設計、 v1.1 で multi-protocol manual の secure-by-default 化。

#### 2026-06-24 新着 (JsonSchema に examples field、 他は contributors 自動更新)

- **JsonSchema に optional `examples` field 追加**: `python-utcp@ae4cebc` からの doc 自動同期で tool input/output JSON Schema model に `examples: Optional[List[JsonType]]`（schema の例値リスト）を追加。 additive optional のため後方互換（commit d583734）
- それ以外の 7 commit は `chore: update contributors data` の自動更新で仕様変更なし

#### v1.0 → v1.1 の変更点

- **`allowed_communication_protocols` 新フィールド**: call template (manual configuration) に optional フィールド追加
- **Secure by default**: 未指定時、 manual は自身のプロトコル種別のツールしか登録/呼び出し不可 (HTTP manual は HTTP tools のみ、 CLI manual は CLI tools のみ)
- **マルチプロトコル明示化**: 複数プロトコル混在 manual は `allowed_communication_protocols` を明示設定する必要がある
- **dual license 明確化**: ライセンス記載を明確化 (commit `29bbc4e`)
- **API docs 同期**: `python-utcp@4ed0a48` から API docs を再同期 (commit `6bd28ae`)

#### v1.1 の破壊的変更

| 変更 | 影響 |
|------|------|
| マルチプロトコル manual の暗黙許可廃止 | v1.0 では HTTP manual に CLI tool を混在登録できたが、 v1.1 では `allowed_communication_protocols` に明示列挙しないとフィルタアウト。 動作する設定が静かに無効化される可能性 |

#### v1.0 の主要な特徴

- **Plugin Architecture**: コア機能を pluggable component に分割、 modularity / testability / packaging 向上
- **Multiple Protocol Support**: HTTP / CLI / WebSocket / Text / **MCP** をプラグイン経由でサポート（MCP も plugin として包摂）
- **Enhanced Data Models**: Pydantic モデルへ統一、 包括的バリデーション
- **Advanced Authentication**: API key / OAuth / カスタム auth など拡張認証
- **Better Error Handling**: シナリオごとの specific exception 型
- **Async/Await Support**: 完全非同期クライアントインタフェース
- **Performance Optimizations**: クライアントとプロトコル実装の最適化
- **OpenAPI 拡張**: agent-focused enhancements（tags、 average_response_size、 multi-protocol、 direct execution instructions）を OpenAPI に追加
- **Dual license clarification**: 直近 commit でデュアルライセンス周りを整理

#### 関連リポジトリ（org エコシステム）

| リポ | 役割 |
|------|------|
| `utcp-specification` | 仕様本体（本サブモジュール） |
| `python-utcp` | 公式 Python 実装 |
| `typescript-utcp` | 公式 TypeScript 実装 |
| `utcp-agent` | 5 行未満で API/native endpoint 直叩きできる ready-to-use agent |
| `code-mode` | MCP/UTCP ツールを **コード実行経由** で呼び出す plug-and-play ライブラリ |

#### MCP との位置関係

| 観点 | MCP | UTCP |
|------|-----|------|
| 呼び出し方式 | proxy server (wrapper) 経由 | agent が native endpoint を直接 |
| latency | wrapper hop あり | hop なし |
| auth/billing | MCP server で再実装 | 既存システムを再利用 |
| 互換性 | MCP プロトコル独自 | OpenAPI 拡張で既存 API 流用 |
| MCP 取り込み | n/a | MCP プロトコルを plugin として包摂 |

#### 参考リンク

- [utcp-specification (GitHub)](https://github.com/universal-tool-calling-protocol/utcp-specification)
- [Universal Tool Calling Protocol org](https://github.com/universal-tool-calling-protocol)
- [www.utcp.io](https://www.utcp.io/)
- [python-utcp](https://github.com/universal-tool-calling-protocol/python-utcp)
- [typescript-utcp](https://github.com/universal-tool-calling-protocol/typescript-utcp)

---

### webmcp-tools

**現行バージョン**: **v0.0.3 (2026-07-17)** (evals-cli `webmcp-evals` も 0.0.3)

**管理**: Google Chrome Labs

**チェックアウト状態**: `7b0feb2` (v0.0.3 + 1 commit = "Refactor of evals cli" #298、 HEAD 2026-07-17)

#### 2026-07-18時点 新着 (Code Mode / execute_batch + WebMCP Polyfill)

- **Code Mode / `execute_batch`**: Page Agent 向けに `execute_batch` tool を公開し "Code Mode" を導入 (#287)
- **WebMCP Polyfill**: ネイティブ非対応ブラウザ向け polyfill を追加し demos へ統合、 cross-origin tool 照会・実行と same-origin チェック改善 (#276)
- **Backend 契約に Gemini/Ollama 追加** (#294)、 **evals-cli 刷新** (runs vs steps バグ修正 + full LLM trajectory 対応, #293, #298)
- **v0.0.3 NPM リリース** (#288/#290)

#### 2026-07-01〜2026-07-06 新着 (navigator.modelContext 削除 + evals-cli 大幅強化)

- **`navigator.modelContext` の削除**: デモ / ドキュメント全体 (AWESOME_WEBMCP.md、 coffee-shop、 doors、 hotel-chain 等) から当該 API 参照を一斉除去 (5944b1e)。 影響はデモ範囲に限定
- **evals-cli 強化（この窓の中心テーマ）**: マルチステップのローカル eval (98373e3)、 openai/ollama プロバイダで Chat Completions API 使用 (ea21765)、 base URL の環境変数上書き (#249)、 期待トラジェクトリでのオプションツール呼び出し (e87b4fe)、 `matchesRecursive` の引数サブセットマッチ (3b0df45)、 OpenAI 互換マルチターンでの Gemini `thought_signature` 保持 (4cfb73d)、 `$pattern` のインラインフラグ `(?flags)` 対応 (1b5ab2f)、 `functionCallOutcome` の省略 `arguments` を未制約扱い (5bed009)
- **デモ更新**: Sport Shop に AI Chat ヘルパー (50a7852)、 result ページのインページエージェント表示 (#250)、 view-transition auto 使用 (6b7223f)
- **依存**: analytics-dashboard デモの js-yaml バンプ (#255)

#### 2026-06-30 新着 (registerTool の Promise 化)

- **registerTool が Promise を返すよう変更**: `document.modelContext.registerTool()` の TypeScript 型定義を `(tool, options?) => void` から `(tool, options?) => Promise<void>` に変更。 登録 promise が reject するケースを適切に扱えるようにし、 全 demo (explainer / hotel-chain / smart-home / shared types `webmcp.d.ts`) の登録呼び出しを `await` + try/catch へ更新。 explainer のコード例・inspector 説明文も `await document.modelContext.registerTool({...})` 表記に修正 (#228)。 戻り値型が `void` → `Promise<void>` に変わるため型を扱う consumer は追随が必要だが、 await しない既存呼び出しは runtime 上従来通り動作するため破壊的変更としては扱わない（「これまで silent だった登録失敗が catch 可能になった」点のみ変化）

#### 2026-06-16〜06-29 新着 (依存バンプのみ)

- **dependabot deps バンプ群**: sport-shop-angular の undici を 7.22.0 → 7.28.0 (#244)、 hono を 4.12.24 → 4.12.25 (#241)、 @sigstore/core を 3.1.0 → 3.2.1 (#248)、 leather-bag の undici を 7.22.0 → 7.28.0 / 6.26.0 → 6.27.0 (#245)、 evals-cli の ws を 8.20.1 → 8.21.0 (#239)

#### 2026-06-24 新着 (in-page agent iframe / SharedWorker 修正 / Stacktree demo)

- **in-page AI agent の iframe サポート** (#243): ページ内 AI agent を iframe 内で実行可能に
- **SharedWorker でのツール実行修正**: SharedWorker 実行時の tool execution を修正
- **iframe agent flow で `getTools` を `executeTool` の前に呼ぶよう修正**
- **Stacktree を Demos に追加** (#246)
- **`document.modelContext` を primary surface として明記** (docs)

#### 2026-06-19 新着 (WebMCP flag リネーム)

- **`enable-features` flag を `WebMCPTesting` → `WebMCP` へリネーム** (#242): Chrome の origin trial / feature flag 名が `WebMCP` に確定したことに伴い、 全 demo / ドキュメントの `enable-features=WebMCPTesting` を `enable-features=WebMCP` に置換

#### 2026-06-16 新着 (shared worker サポート / dependabot 群)

- **shared worker サポート追加**: french-bistro demo に shared worker サポートを追加 (#224)、 shared worker で port を clean up（`delete` 非使用へのリファクタ含む）
- **dependabot deps バンプ群**: leather-bag の Angular 一式 (compiler / common / core / forms / platform-browser / router / build / compiler-cli) を 22.0.1 へ (#230, #232, #234)、 smart-home / hotel-chain の vite 8.0.x → 8.0.16 (#235, #236)、 evals-cli/ui の js-yaml 4.1.1 → 4.2.0 (#238)、 sport-shop-angular の Angular 群 (#234)

#### 2026-06-15 新着 (origin trial tokens / dependabot 群)

- **demos に origin trial token 補完**: 欠落していた origin trial tokens を demos に追加 (ot2、 #229)
- **dependabot deps バンプ群**: react-flightsearch (#227)、 evals-cli/ui (#226)、 webmcp-maze (#225) の esbuild / vite / @vitejs プラグインを bump、 leather-bag の hono 4.12.18 → 4.12.23 (#213)、 hotel-chain の postcss 8.5.8 → 8.5.15 (#210)

#### 2026-06-10 新着 (leather-bag angular standards / referrer)

- **leather-bag app を最新 Angular standards へ更新**: leather-bag demo を最新の Angular 流儀へリファクタ
- **referrer 利用対応**: use-referrer の取り込み (#223)
- **demo 依存バンプ**: sport-shop-angular の hono 4.12.24 / analytics-dashboard の postcss 8.5.15 を dependabot でバンプ (#216, #217)

#### 2026-06-09 新着 (Angular 22 / parametersJsonSchema / french-bistro agent)

- **french-bistro demo に in-page agent 追加** (#214)
- **`parametersJsonSchema` へ移行**: tool 定義で `parameters` に代わり `parametersJsonSchema` を使用 (#220)
- **leather-bag demo を Angular 22 へ更新**: Angular 流の WebMCP tools 公開、 dynamic form 挙動の追加

#### 2026-06 新着 (Page Agent demo / Sport Shop evals / permission policy)

- **permission policy 厳格化**: permission policy を tighten
- **Page Agent demo 追加**: Page Agent デモを追加
- **Sport Shop evals**: Sport Shop の example evals 追加、 pickup / promos / 追加カートツールを Sport Shop に追加
- **Pizza-Maker tools クロスオリジンテスト公開**: cross origin testing 向けに Pizza-Maker tools を公開
- **eval レポート改善**: eval 名付きのレポート改善、 sidecar UI 改善
- **AWESOME_WEBMCP に webmcp.cool 追加**: AWESOME_WEBMCP.md に webmcp.cool を追加

#### 最近の変更点

- **Search product 全体公開ツール化**: Search product をグローバルに利用可能なツールへ昇格
- **french-bistro tool 説明更新**: french-bistro デモのツール説明改善
- **input schema 削除**: 不要な input schema を削除
- **sport shop search results ツール**: スポーツショップで検索結果を読むツール追加
- **demo サイト表記削除**: 「demo site」表現を削除（プロダクト感の向上）
- **より複雑な hotel example**: ホテル検索の複雑化、 検索ロジック修正
- **autocomplete values 追加**: name/phone form フィールドへの autocomplete 値追加 (#159, #160)
- **Leather Bag デモ修正**: Leather Bag デモのイメージ修正 (#155)
- **registered-purchase 機能**: registered-purchase 機能追加 (#149)
- **unregisterTool 削除**: unregisterTool 呼び出し削除 (#153)
- **untrustedContentHint 追加**: `shared/types/webmcp.d.ts` に untrustedContentHint 追加 (#152)
- **Pizza toppings 修正**: (#150)
- **Live demo リンクフォーマット修正**: README の live demo リンクフォーマット修正
- **Flight Search flexible routes**: フライト検索のフレキシブルルート対応・one-way/round-trip 対応 (#141)
- **Flight Search build 修正**: return flight properties をオプショナル化 (#144)
- **french-bistro demo Lighthouse 改善**: Lighthouse audit スコア改善
- **Morning ritual coffee demo**: persistent state と index entry 付きで実装（一時的に revert 状態）
- **Maze player trail animation 修正**: 迷路プレイヤーの軌跡アニメーション修正 (#133)
- **Label `for` attribute オプション**: アクセシビリティ改善 (#146)
- **依存関係更新**: Hono 4.12.14、basic-ftp 5.3.0、protobufjs 7.5.5、vite 8.0.5、vite 7.3.2 等

#### 主要な変更点

- **Order Tracking 宣言的デモ**: オーダートラッキングの宣言的デモ追加
- **Ticket Booking サポート**: チケット予約サポート追加
- **webmcp-maze デモ**: 新規迷路デモプロジェクト追加
- **WebMCP Flow**: アーキテクチャダイアグラムビルダー追加
- **Vercel AI SDK 移行**: 実験的マルチステップツール実行付き Vercel AI SDK への移行
- **Sport Shop デモ**: スポーツショップデモの改善

#### 参考リンク

- [webmcp-tools](https://github.com/GoogleChromeLabs/webmcp-tools)

---

## Payments / Agentic Commerce

決済 / agentic commerce 関連プロトコルとその仕様。 既存の generic protocols と分離して管理（`payments/` ディレクトリ配下）。 軸は次の 4 つ:

1. **Commerce flow**: ACP / AP2 / UCP — 注文 / カート / 支払いハンドラ等の業務プロトコル
2. **Crypto-native payment**: x402 — HTTP ネイティブ暗号通貨決済
3. **Agent identity (cryptographic verify)**: Visa Trusted Agent Protocol、 Mastercard Verifiable Intent — 大手金融プレイヤーが回す agent identity / authorization の cryptographic 証明標準
4. **業界横断パートナーシップ**: AP2 と Verifiable Intent の周りに Adyen / Worldpay / Fiserv / Checkout.com / Basis Theory / Amex / JCB / PayPal などほぼ全大手が集結

---

### ACP (Agentic Commerce Protocol)

**現行バージョン**: API Version 2026-04-17

**管理**: OpenAI & Stripe

**チェックアウト状態**: `c2afc86` (タグなし継続デプロイ、 v2026-04-17 API 後の HEAD、 HEAD 2026-06-15)

#### v2026-04-17 後の変更点

- **IntentTrace / CancelSessionRequest の embedded examples 改善** (2026-06-15、 #253): 2 つの embedded example を改善
- **`delegate_payment` OpenAPI examples の error envelope unwrap** (2026-06-15、 #266): released delegate_payment の OpenAPI example で error envelope を unwrap
- **2026-01-16 changelog を readme listing に追加** (2026-06-15、 #251): readme の changelog 一覧に欠落していた 2026-01-16 分を追加
- **MessageInfo / MessageWarning / MessageError の examples 修正** (2026-06-11、 #262): 3 種メッセージ型 (`MessageInfo` / `MessageWarning` / `MessageError`) の examples を正しい形へ修正
- **SEP: Feed API Upsert Products Response に Feed Update ID 追加** (2026-06-04、 #260)
- **Fulfillment Details on Checkout Complete (SEP)**: チェックアウト完了時に履行詳細（fulfillment details）を返却できるよう許可する SEP (#200)
- **Suggested Pricing on Checkout Create (SEP)**: チェックアウト作成時に suggested pricing を提示できるようにする SEP (#201)
- **`delegate_payment` OpenAPI examples error envelope 修正**: `delegate_payment` の OpenAPI 例で error envelope を unwrap する形に修正 (#243)
- **refund amount example スキーマ整合**: spec/2026-01-30 の refund amount example の型を schema に合わせる修正 (#249)
- **Stale PR Reminder Workflow**: PR が古くなったときに reminder を送る workflow を追加 (#240)
- **Order Schema Post-Checkout SEP**: チェックアウト後の Order Schema アライメント SEP (#232)
- **`UpsertProductsResponse` JSON Schema 追加**: feed JSON Schema バンドルに `UpsertProductsResponse` 追加 (#241)
- **Meta TSC メンバー追加**: Meta を TSC メンバーに追加 (#236)
- **Address.company 説明修正**: コピーペーストエラー修正 (#193)
- **`intervention_required` ドキュメント追加**: RFC エラーコードドキュメントに `intervention_required` 追加 (#143)
- **intent traces examples**: 全 reason code の intent traces 例追加 (#151)
- **Agentic Commerce Inc. CLA 署名**: Catalog 関連で Agentic Commerce Inc. を Corporate CLA 署名者に追加 (#226)

#### v2026-04-17 の主要な変更点

- **Cart Capability SEP**: Cart Capability 追加 (#188)
- **Product Feeds API SEP**: Product Feeds API 追加 (#190)
- **Marketing Consent SEP**: マーケティング同意フロー追加 (#199)
- **Markdown Content Specification (CommonMark)**: Markdown コンテンツ仕様策定 (#212)
- **Payment Intent (capture vs authorize)**: PaymentHandler `display_name` 含む支払い意図 (#130)
- **Payment Handler 表示順序**: マーチャント提案の表示順序サポート (#133)
- **Mandatory Idempotency Requirements**: 冪等性要件と保証の義務化 SEP (#121)
- **Rich Post-Purchase Lifecycle Tracking**: Order スキーマに購入後ライフサイクル追跡追加 (#106)
- **Discovery RFC seller terminology**: discovery RFC を seller 用語に再構成 (#176)
- **TSC Operating Model**: TSC 運営モデルドキュメント追加 (#184)
- **CLA 署名者追加**: Meta Platforms, Affirm, PayPal, Agentic Commerce (Catalog) が CLA 署名
- **`risk_signals` 仕様修正**: `delegate_payment` で空の risk_signals を許可 (#214)
- **ガバナンスモデル改訂**: TSC, DWGs を含むガバナンス構造の見直し (#173)
- **Webhook Signing Replay Protection 強化**: リプレイ攻撃防止の強化 (#160)
- **Delegated Authentication API**: マーチャント指定認証の API コントラクト (#93)
- **Discovery Well-Known Document 実装**: (#137)
- **MCP Transport Binding**: Agentic Checkout 向け MCP トランスポートバインディング (#139)

#### v2026-01-30 の主要な変更点

- **Capability Negotiation**: エージェントとセラー間の機能ネゴシエーション
- **Payment Handlers Framework**: 構造化された支払いハンドラー（**破壊的変更**）
- **Extensions Framework**: オプション・コンポーザブルな拡張機能
- **Discount Extension**: リッチな割引コードサポート（初のACP拡張）

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| Payment Handlers 導入 (v2026-01-30) | 支払い方法IDから構造化ハンドラーへ移行必須 |
| `items` → `line_items` | Create/Update リクエストのフィールド名変更 |
| `currency` 必須化 | create リクエストで必須フィールドに |
| `channel` フィールド削除 (#85) | `AuthenticationMetadata` からの削除 |

#### 参考リンク

- [ACP Protocol](https://agenticcommerce.dev)

---

### AP2 (Agent Payments Protocol)

**現行バージョン**: v0.2.0 (2026-04-28)

**管理**: Google Agentic Commerce

**注目**: 2026-04-28 に **v0.2.0 リリース**。`Release of V2 (#233)` として AP2 V2 仕様の正式リリースに到達。 PayPal / Adyen / Amex / Mastercard / JCB / Worldpay 等 60+ パートナーが集結する業界横断ハブ。

#### v0.2.0 後の変更点

- **uvlock 削除**: uv.lock を repository から除外 (#246)
- **CHANGELOG.md 更新**: 0.2.0 リリースに合わせた CHANGELOG 更新 (#239)
- **動画タイトル更新**: README 動画タイトル修正 (#238)
- **CONTRIBUTING.md 更新**: コントリビューションガイドライン更新 (#240)

#### v0.1.0 → v0.2.0 の主要な変更点

- **AP2 V2 リリース**: V2 仕様の正式リリース (#233)
- **PaymentReceipt**: トランザクション確認オブジェクト実装 (#110)
- **X402 決済**: x402 payment method 統合（Python サンプル） (#121)
- **Go サンプル**: スタンドアロン Go 実装例 (#101)
- **Vertex AI 認証**: Google API キーに加えて Vertex AI 認証サポート追加 (#48)
- **X-A2A-Extensions ヘッダーロギング**: サーバーミドルウェアでヘッダーロギング (#29)
- **UCP 統合ドキュメント**: Universal Commerce Protocol 連携 (#138)
- **Kite AI / Global Payments / Tether / Solana / OKX / Nexi**: 多数のパートナー追加

#### 参考リンク

- [AP2 Protocol](https://github.com/google-agentic-commerce/AP2)

---

### UCP (Universal Commerce Protocol)

**現行バージョン**: v2026-04-08 (2026-04-13)

**チェックアウト状態**: `5a36927` (`git describe` = `v2026-01-23-178-g5a36927`。 リリースタグ v2026-04-08 は現 HEAD から到達不能な別ライン = release-branch 運用のため describe は祖先タグ v2026-01-23 起点、 HEAD 2026-07-17。 新タグ未作成)

#### 2026-07-18時点 新着 (keys[] 昇格 = 破壊的 / governance workflow 整備)

- **`keys[]` を canonical な profile 署名鍵フィールドに昇格 (#566, 2026-07-12, 破壊的)**
- **spec に per-operation の Requirement 列を追加** (#542)
- **governance**: governance workflow 追加・CODEOWNERS 削除 (#583)、 MAINTAINERS.md を中央 repo へ redirect (#598)、 重複 merchant_fulfillment_config を canonical business config へ統合 (#581)

| 破壊的変更 | 影響 |
|------|------|
| `keys[]` を canonical 署名鍵フィールドに昇格 (#566) | profile の署名鍵参照方法が変更、 旧フィールド利用側は移行必要 |

#### 2026-07-02〜2026-07-03 新着 (Web Bot Auth 相互運用 + 名前空間権限バインディング規範化)

- **Web Bot Auth (WBA) 相互運用** (#483): 署名鍵 JWK スキーマと署名仕様に **EdDSA (Ed25519, [RFC 8037](https://datatracker.ietf.org/doc/html/rfc8037)) をオプションアルゴリズムとして追加**。 ECDSA P-256 (ES256) は UCP ベースラインとして維持。 WBA 相互運用を選ぶ検証者は EdDSA サポートが MUST（WBA が Ed25519 を必須とするため）。 後方互換
- **名前空間権限バインディングの定義 + RDNS 文法拡張** (#530): 宣言スキーマ URL を逆ドメイン権限へ束縛する正規手順を規定（URL パーサ使用・https 必須・userinfo 拒否・登録ドメイン要求・ラベル逆順で authority_prefix 生成）。 従来「MUST validate」と「SHOULD reject」で矛盾していた規範文を解消 — 名前空間なりすまし防止の規範強化
- **docs: "Capabilities Incompatible" の例を `capabilities_incompatible` に修正** (#562)

#### 2026-06-30 新着 (スキーマ参照表の配列ラベル修正 / catalog REST ヘッダー追記)

- **catalog REST に HTTP Headers セクション追加**: catalog REST バインディング (`docs/specification/catalog/rest.md`) に「HTTP Headers」節を新設。 全操作共通で `UCP-Agent` ヘッダーを MUST とし、 Dictionary Structured Field 構文 ([RFC 8941](https://datatracker.ietf.org/doc/html/rfc8941)) でプラットフォームプロファイル URI (`profile="https://platform.example/profile"`) を載せる旨を明記 (#548)
- **スキーマ参照表: 配列要素を型名でラベル付け (旧 `Array[any]` を解消)**: `allOf` 定義や解決時の `$ref` インライン化で要素型をインラインに読めない配列プロパティが、 参照表で `Array[any]` と描画されていた不具合を修正。 AP2 / buyer consent / discount / fulfillment / split payments 各拡張 capability 表の totals、 および catalog lookup の products の計 11 セルが `Array[Total]` / `Array[Product]` と正しく描画されるようになった。 スキーマ定義自体は base から不変で、 参照表の描画 (`main.py`) のみの修正 (#552)

#### 2026-06-29 新着 (CI/ツーリングのみ)

- **workflow path triggers 更新 & コンフリクト解消**: docs / linter ワークフローの path trigger 調整、 cspell カスタム辞書・pre-commit 設定の微修正。 仕様・スキーマの変更なし (#232)

#### 2026-06-26 新着 (fulfillment methods を catalog へ 破壊的 / docs / Tech Council)

- **BREAKING: fulfillment methods を catalog surface に展開** (#507、 `feat!`): `dev.ucp.shopping.fulfillment` を checkout だけでなく catalog surface (search / lookup / get_product) にも合成し、 variant が `fulfillment.methods[]` で受け取り方法を広告（method-first discovery、 shipping/pickup を peer method 化）。 checkout の閉じた `type` enum を open string vocabulary 化（well-known: shipping / pickup、 未知値は無視）し、 destinations を単一形状 `{ id, name?, address?, availability }` へ再構成
- **schema reference: inline `oneOf` branch レンダリング修正** (#549)
- **Error Handling docs: `message.path` field 規約追加** (#397)
- **embedded session error を `params.error` 配下に wrap** (#494、 examples 修正)
- **common types を shared references セクションへリンク** (#536)
- **README に schema / documentation development 手順を追加** (#452)
- **site nav**: announcements セクション追加 (#529)、 overview nav 末尾へ移動 (#539)
- **Tech Council メンバー交代**: Naga Malepati → Uddhav Kambli (#541)

#### 2026-06-19 新着 (path field 記述統一 / Booking.com ロゴ / CI)

- **message schema 間で path field の記述を統一** (#380): 各 message schema にまたがる `path` フィールドの description を harmonize（docs）
- **Booking.com SVG ロゴを新ブランディング版へ更新** (#526、 style)
- **ucp-schema caching 修正** (#522、 ci): CI の ucp-schema キャッシュ不具合を修正

#### 2026-06-17 新着 (catalog example validation refactor / docs / AGENTS.md)

- **catalog examples を op + direction で検証し `def=` を廃止** (#516): catalog example のバリデーションを operation + direction 単位へリファクタし `def=` を除去
- **AGENTS.md 追加**: coding assistant 向け AGENTS.md を追加 (#510)
- **docs 群**: signatures.md の footnote レンダリング改善とテーブル整列 (#291)、 Create Checkout から cart_id を cross-link (#439)、 get_product の catalog error severity note を qualify (#464)、 schema reference page で Catalog response metadata をレンダリング (#465)、 REST binding に欠落していた Discovery セクション追加 (#509)
- **ci**: node 24 互換のため GitHub Actions を bump (#521)

#### 2026-06-15 新着 (build script 改善)

- **build script 出力に serving instructions 追加**: build script の出力末尾に serving instructions を追加 (#432)

#### 2026-06-12 新着 (buyer consent per-segment 破壊的 / delegated IdP)

- **BREAKING: buyer consent に per-segment extensibility** (#451): buyer consent を per-segment で拡張可能に。 `feat!` のため後方互換を破る変更
- **delegated identity providers + accelerated IdP flow** (#423): delegated identity provider と高速化された IdP フローを追加
- **get_order に signature response headers 追加**: 欠落していた署名レスポンスヘッダを `get_order` に追加 (#370)
- **embedded schemas レンダリング時の required フィールド保持**: 埋め込みスキーマのレンダリングで required フィールドを保持 (#501)
- **Google TC メンバー交代**: Venu → Jing (#506)
- **docs 修正**: checkout の不要な fulfillment-option entity 削除 (#284)、 identity linking の formatting 修正 (#505)、 cart の error response examples で無効な UCP version を訂正 (#504)

#### 2026-06 新着 (split payments extension / idempotency 契約)

- **split payments extension 追加**: 分割支払い拡張を導入（discount / loyalty に続く拡張） (#409)
- **idempotency payload-mismatch 契約明文化**: idempotency の payload 不一致時の契約を明文化 (#485)
- **Amadeus ロゴ刷新**: lodging セクションで Amadeus ロゴを強調 (#488)、 legacy Amadeus SVG を更新版に置換 (#468)
- **stylelint / SVG フォーマット修正**: local_preview と site ディレクトリを stylelint 対象外に (#495)、 pre-commit SVG formatting と trailing newline 修正 (#491)

#### v2026-04-08 後の変更点

- **`feat`: loyalty extension for catalog/cart/checkout capability**: ロイヤルティ拡張を catalog / cart / checkout capability に追加（discount 拡張に続く 2 つ目の正式拡張） (#340)
- **schema-validated documentation examples**: ドキュメント例を schema 検証ベースに整備 (#359)
- **partner ロゴ群追加**: documentation assets に partner logos と configuration 追加、 logo フォーマットと layout を整理 (#453)
- **idna / pymdown-extensions 依存バンプ**: idna 3.11 → 3.15 (#457)、 pymdown-extensions 10.21.2 → 10.21.3 (#456)
- **PR auto-labeler permissions 修正**: PR auto-labeler の権限を修正 (#454)
- **schema refactor**: schema references を common types に整理 (#436)
- **profile schemas 検証修正（破壊的）**: profile schemas をバリデーションと endpoint contract に合わせて修復、 後方互換を破るスキーマ訂正 (#429)
- **urllib3 v2.7.0 セキュリティバンプ**: urllib3 2.6.3 → 2.7.0 (#434)
- **build_local.sh のサーバー起動削除**: build_local.sh から server start を除去 (#430)
- **Identity Linking OAuth 2.0 基盤**: capability-driven scopes をベースとした identity linking の OAuth 2.0 foundation 追加（**破壊的変更**） (#354)
- **attribution フィールド追加**: platform referral context 用の attribution フィールド追加 (#391)
- **core-concepts 拡充**: 包括的な UCP プロトコル概要を core-concepts ドキュメントに統合 (#336)
- **glossary / acronym 標準化**: 中央集約型の glossary と acronym standards 追加 (#241)
- **deprecated checkout id 修正**: playground payload から deprecated checkout id を omit (#332)
- **法人レジストリブロック**: corporate registries のブロック (#411)
- **typo / formatting 修正**: index と versioning ドキュメントの typo 修正と formatting 改善 (#416)
- **Twum Djin ガバナンス評議会追加**: Governance Council に Twum Djin 追加 (#395)
- **Configure Site URL 共通アクション化**: CI ステップを composite action に抽出 (#382)
- **拡張性・前方互換ガイドライン追加**: ドキュメントに extensibility と forward compatibility ガイドライン追加 (#290)
- **discounts 拡張スキーマ修正**: ドキュメント例と discounts 拡張スキーマの不整合修正 (#371)
- **Tech Council メンテナーリスト更新**: メンテナー一覧更新
- **legacy PR テンプレート削除**: (#377)
- **signatures.md テキストダイアグラム現代化**: (#331)
- **create_cart `ucp_agent` パラメータ修正**: REST オペレーションで欠落していた `ucp_agent` パラメータ追加 (#362)
- **Total/Totals フィールドレンダー修正**: schema reference page で Total/Totals が表示されない問題修正 (#352)
- **MCP レスポンス例 entity wrapper 削除**: MCP レスポンス例から不要な entity wrapper を除去 (#360)
- **ドキュメント正確性修正**: 仕様例の inconsistency / accuracy 修正 (#363, #365)
- **Profile 例修正**: Playground widget 内の profile examples 修正 (#236)
- **lockfile package registries 標準化**: lockfile の package registries 標準化 (#368)
- **super linter アップグレード**: (#372)
- **PR auto-labeler 追加**: (#366)
- **line item ids の識別差別化**: line item ids と item ids を区別 (#112)

#### v2026-04-08 の主要な変更点

- **`variant.selected_options` → `options` リネーム**: variant のオプションフィールドリネーム (#353)（**破壊的変更**）
- **Webhook フィールド分離**: dangling webhook フィールドをヘッダーに分離、トランスポートがベーススキーマのみ参照するよう変更 (#342)（**破壊的変更**）
- **UCP エラーコンベンション統一**: 埋め込みプロトコルエラーを UCP エラーコンベンションに統一 (#325)（**破壊的変更**）
- **Get Order オペレーション**: platform-auth 付き Get Order 操作追加 (#276)
- **Order `currency` 必須化**: Order スキーマで currency を必須フィールドに変更 (#283)（**破壊的変更**）
- **Order Capability 更新**: Order capability の更新 (#254)（**破壊的変更**）
- **`signed_amount.json` 使用**: total で signed_amount.json を使用するよう修正 (#299)（**破壊的変更**）
- **Order `label` フィールド**: Order にオプションの `label` フィールド追加 (#326)
- **Identity Linking リバート**: Identity Linking リデザインのリバート (#329)
- **lodash セキュリティ修正**: Trivy 脆弱性修正のための lodash 更新 (#333)
- **Transition Schema クリーンアップ**: バージョンカット準備のための transition schema 整理 (#341)
- **EP core 抽出**: 共有 EP core の抽出とナビゲーションでのトランスポートグルーピング (#339)

#### v2026-01-23 後の改善（v2026-04-08 に含まれる）

- **Embedded Protocol Transport Binding**: カートケイパビリティ向け埋め込みプロトコルトランスポートバインディング＋再認証メカニズム (#244)
- **Product Get Operation**: `catalog.lookup` の get product オペレーション追加 (#195)
- **Discount Capability 拡張**: カートへの割引機能拡張 (#246)
- **Eligibility Claims & Verification**: 適格性主張と検証コントラクト (#250)
- **Authorization & Abuse Signals**: 認可と不正利用シグナルの形式化 (#203)
- **Catalog Search & Lookup**: 製品ディスカバリー用カタログ検索・参照機能 (#55)

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| fulfillment methods を catalog へ展開 (#507, 2026-06-26) | checkout の閉じた `type` enum を open vocabulary 化、 fulfillment を catalog surface に合成、 destinations を単一形状へ再構成。 method-first discovery への移行 |
| profile schemas 検証修正 (#429, v2026-04-08 後) | profile schemas の互換破壊的訂正、 既存実装の再検証必要 |
| Identity Linking OAuth 2.0 foundation (#354, v2026-04-08 後) | capability-driven scopes へ移行、認可フロー再設計 |
| `variant.selected_options` → `options` (#353) | variant フィールド名変更 |
| Webhook フィールドヘッダー分離 (#342) | トランスポートスキーマ構造変更 |
| EP エラーコンベンション統一 (#325) | エラーレスポンス形式変更 |
| Order `currency` 必須化 (#283) | Order 作成時に currency 必須 |
| Order Capability 更新 (#254) | Order capability 構造変更 |
| `signed_amount.json` 使用 (#299) | total 形式変更 |
| Embedded Protocol Transport Binding (#244) | カートケイパビリティ向けトランスポート＋再認証 |
| Authorization & Abuse Signals (#203) | 認可シグナルの構造変更 |

#### 参考リンク

- [UCP Protocol](https://github.com/Universal-Commerce-Protocol/ucp)

---

### x402 (Internet Native Payments)

**現行バージョン**: Go v2.9.0 / Python v2.7.0 / TypeScript npm-@x402/\* v2.10.0 (npm-x402@v1.1.0 legacy バンドル含む)

**注目**: リポジトリが foundation repo に移動中。README にリポジトリ移動ノート追加 (#40)、main ブランチを foundation repo に合わせる形で bump (#93)。

#### Go v2.9.0 の主要な変更点

- **`SettleResponse`/`VerifyResponse` Extensions フィールド**: TypeScript SDK パリティのための Extensions フィールド追加 (#1808)
- **net/http サポートドキュメント**: Go SDK ドキュメントに net/http サポート追加 (#1782)

#### TypeScript Core v2.10.0 の主要な変更点

- **Aptos サポート**: Aptos ブロックチェーンサポート追加
- **Stellar サポート**: Stellar ブロックチェーンサポート追加
- **hook types エクスポート**: hook types のエクスポート (#1811)
- **MCP structuredContent 保持**: payment wrapper result での structuredContent 保持修正 (#1834)

#### Python v2.7.0 の主要な変更点

- **MCP server_sync テストカバレッジ**: MCP server_sync モジュールのテストカバレッジ追加 (#1733)

#### 未リリースの変更点

- **Stable テストネットサポート**: EVM に Stable テストネット (chain ID 2201) サポート追加 (#1786)
- **EVM コントラクトデプロイ修正**: EVM コントラクトデプロイの修正 (#1880)
- **USDC 追加**: Arbitrum One/Sepolia に USDC 追加 (#1877)
- **HTTPFacilitatorClient 308 リダイレクト修正**: 308 リダイレクト対応修正 (#1813)
- **Facilitator signer ランダム選択修正**: signer 選択のランダム化修正 (#1849)
- **Polygon メインネット**: Polygon メインネット (chain ID 137) デフォルトアセットサポート追加 (#1791)
- **リポジトリ移動通知**: README にリポジトリ移動ノート追加 (#40)

#### 参考リンク

- [x402 Protocol](https://github.com/coinbase/x402)

---

### Visa Trusted Agent Protocol

**現行バージョン**: 初期スペック + sample 実装（タグなし、 commit 6 件、 2026 年内に立ち上げ）

**管理**: Visa Inc.（クレジットカード大手）

**注目**: Agentic commerce での **agent identity / authorization 標準化**。 既存の payments 系（ACP / AP2 / UCP / x402）の **identity 補完レイヤ** として位置。 大手金融プレイヤー（Visa）が回した数少ない agentic commerce identity 標準。

#### 主要な特徴

- **Cryptographic Identity Proof**: AI エージェントが merchant に対し、 自身の identity と user 委任権限を **暗号署名** で証明
- **署名コンテンツ**: timestamp / unique session identifier / key identifier / algorithm identifier を含む（リプレイ防止）
- **Context-Bound Security**: 全リクエストが merchant の **specific website + 操作中の正確なページ** に cryptographically lock。 認可の他所流用を不可能化
- **Replay 攻撃防止**: time-sensitive elements でリクエスト毎にユニーク化、 1 回限り有効
- **Customer / Payment Identifier 標準伝達**: 同意済み consumer の **PAR (Payment Account Reference)**、 verifiable consumer identifier、 loyalty number、 email、 phone などを query parameter 経由で merchant へ安全配信
- **Browse / Payment 双方の認可**: ブラウジングと支払いそれぞれの操作種別ごとに署名 bound
- **Anti-Fraud**: 認証済み agent と anonymous bot の区別を明確化、 chargeback / 不正取引削減

#### リポ構成

- 仕様 + sample 実装 (Quick Start で multiple components)
- **nonce validation サンプルコード** 追加済み（リプレイ防止検証実装の参考）

#### 参考リンク

- [visa/trusted-agent-protocol (GitHub)](https://github.com/visa/trusted-agent-protocol)

---

### Mastercard Verifiable Intent

**現行バージョン**: v0.1.0 (Draft)、 直近 push 2026-04-20、 v0.1.0 タグから +4 commits

**管理**: Mastercard（共同開発: Google）

**注目**: 2026-03-05 オープンソース化。 Visa Trusted Agent Protocol と並ぶ大手金融プレイヤーの agent identity / authorization 標準。 **SD-JWT (Selective Disclosure JWT) ベース**の cryptographic credential chain で「user → agent への delegation scope」を tamper-evident に証明。 AP2 / UCP との相互運用を明示的に設計（rival ではなく complementary）。

#### 主要な特徴

- **SD-JWT credential format**: Selective Disclosure 機構により、 必要最小限の情報だけを各 party に開示（プライバシー保護寄り）
- **Layered tamper-evident chain**: AI agent の commercial action が user delegation scope 内であることを cryptographic に証明
- **2 つの実行モード**:
  - **Immediate**: user が都度確認（user-confirmed）
  - **Autonomous**: agent に委任（agent-delegated）
- **標準ベース**: FIDO Alliance / EMVCo / IETF / W3C
- **AP2 / UCP との相互運用**: complementary 標準として設計
- **Reference 実装**: Python 100% で公式 reference implementation 同梱

#### 業界コミットメント (2026-03-05 発表時)

| 企業 | 役割 |
|------|------|
| Google | 共同開発 |
| Fiserv / IBM / Checkout.com / Basis Theory / Getnet | 支持表明 |
| Adyen / Worldpay (Global Payments) | 支持表明 |

#### 参考リンク

- [agent-intent/verifiable-intent (GitHub)](https://github.com/agent-intent/verifiable-intent)
- [verifiableintent.dev](https://verifiableintent.dev/)
- [Verifiable Intent spec overview](https://verifiableintent.dev/spec/)
- [Mastercard - Verifiable Intent](https://www.mastercard.com/global/en/news-and-trends/stories/2026/verifiable-intent.html)

---

### 既存 commerce 系プロトコル位置関係まとめ（横断比較）

| プロトコル | 担当領域 | 管理 |
|-----------|---------|------|
| **ACP** (Agentic Commerce Protocol) | Order / Cart / Payment Handler レイヤ | OpenAI + Stripe |
| **AP2** (Agent Payments Protocol) | Payment Receipt / Payment method 統合 | Google + 60 partners |
| **UCP** (Universal Commerce Protocol) | Cart / Catalog / Order / Discount / Identity Linking | Universal Commerce Protocol コミュニティ |
| **x402** | Crypto-native HTTP payment | Coinbase |
| **Visa Trusted Agent Protocol** | Agent identity / authorization の cryptographic proof（merchant 側 verify） | Visa |
| **Mastercard Verifiable Intent** | SD-JWT chain で user → agent delegation scope を verify（プライバシー保護寄り） | Mastercard + Google |

---

## Google Cloud / ADK

### ADK Python

**現行バージョン**: **v2.5.0 (2026-07-16)** / v1.36.1 (2026-07-06, stable lts)

**チェックアウト状態**: `d27b4cd9` (OSS mirror main の HEAD、 HEAD 2026-07-17。 Copybara export + squash-sync 運用のため v2.x タグは main の直系祖先に無く、 `git describe` は最後の到達タグ `v1.32.0-747-gd27b4cd9` を表示するが、 main の CHANGELOG 先頭は 2.5.0 世代でありコードも 2.5.0 世代。 バージョン参照は明示タグ/CHANGELOG を正とする)

#### 2026-07-18時点 新着 (v2.5.0 タグ発行: ManagedAgent 拡充 / Skill Registry / mTLS 全面化)

- **v2.5.0 (2026-07-16)**: v2.4.0 → v2.5.0 へ更新
- **ManagedAgent (Managed Agents API backed)**: `single_turn` mode、 remote MCP server 対応、 node_input→user_content bridging (2.4.0–2.5.0)
- **Workflow resumability / HITL**: task-mode workflow node の state-based resumption、 standalone node と NodeTool の HITL resumption、 resumability checkpoint (2.3.0–2.5.0)
- **Skill / Agent Registry**: `GCPSkillRegistry`、 search agents と search MCP servers の registry 追加 (1.34.0, 2.5.0)
- **mTLS 全面対応 + セキュリティ修正**: Google API tools / DiscoveryEngineSearchTool / telemetry exporter の mTLS、 SSRF・artifact path traversal・tool confirmation continuation forgery・starlette CVE 対応 (2.4.0–2.5.0)
- **破壊的**: OpenTelemetry Events API/SDK deprecation に伴い event logger setup を削除 (2.5.0) — Events API 経由の telemetry 設定は無効化

#### 2026-07-02〜2026-07-07 新着 (v2.4.0 / v1.36.1 タグ発行 + main 67 commits: Workflow as Tool / ManagedAgent / セキュリティ硬化)

**リリース**: release ブランチ上で **v2.4.0 (2026-07-07)** と **v1.36.1 (2026-07-06, stable lts)** のタグが発行された（mirror main には CHANGELOG 未反映のため詳細内訳は次窓で確認）。 以下は main 側 +67 commits の主要変更（Copybara export のため PR 番号なし、 short hash 参照）:

- **Workflow as Tool コア機能**: workflow をツールとして呼び出す中核実装 (1263ed64)
- **ManagedAgent**: Managed Agents API 経由の ManagedAgent 追加 (cf91b844) + サンプル
- **`model_input_context`**: LLM リクエストの一時コンテキストを追加 (2aeb1e1b)
- **mTLS 対応の拡大**: GDA クライアント / Google API tools (e85a7b28, 3466586b)、 OAuth2 トークン要求での mTLS エンドポイント使用 (ffe41f05)
- **DaytonaEnvironment**: リモートサンドボックス作業環境の追加 (df6baf4a)
- **McpToolset**: configurable parameter を property として公開 (cca8c567)
- **BigQuery**: tool description/parameter schema の LLM_REQUEST ログ出力 (ecef5f85)、 analytics view に thinking / tool-use トークン列を公開 (c14258df)
- **Telemetry**: `gen_ai.invoke_agent.{inference,tool}_calls` メトリクス追加、 schema v2 での invoke_workflow span。 **注意: `gen_ai.agent.workflow.steps` と `gen_ai.agent.{request,response}.size` の削除、 duration メトリクスの GenAI semconv 名への改名あり — 既存ダッシュボード / アラートに影響し得る**
- **SECURITY**: GcsArtifactService / InMemoryArtifactService の**パスセグメント検証でクロスユーザー artifact アクセスを防止** (8718aeff)、 **artifact 参照を呼び出し元スコープに制限** (f8631500)、 **_OriginCheckMiddleware への DNS リバインディング保護追加** (9a4f479d)、 gepa サンプルの Jinja2 autoescape 有効化（XSS 対策、 a721c1eb）
- その他: `SKIP_THOUGHT_SIGNATURE_VALIDATOR` 定数公開 (6aad10df)、 OAuth prompt パラメータ設定を許可 (ac997706)

#### 2026-07-01 新着 (v2.3.0 開発 mainline +43 commits: telemetry schema v2 / Anthropic effort / LiteLLM 拡充 / mTLS 硬化)

前回文書点 `50c81ebf` (2026-06-27) から HEAD `17d5f389` (2026-07-01) まで 43 commits (2026-06-29〜07-01 に集中)。 Copybara export のため commit subject に `#PR` は付与されず、 short hash で参照する。 主要なもの:

**[Features]**

- **telemetry: invoke_agent 呼び出し数メトリクス**: `gen_ai.invoke_agent.inference_calls` / `gen_ai.invoke_agent.tool_calls` を追加 (semconv #336 準拠、 per-span TelemetryContext でカウント) (c6dec00a)
- **telemetry: schema version opt-in**: 環境変数 `ADK_TELEMETRY_SCHEMA_VERSION_OPT_IN` (1|2) を導入。 Agent Engine 上 (`GOOGLE_CLOUD_AGENT_ENGINE_ID` 存在時) は 2、 それ以外は 1 が既定 (84bbb357)
- **Anthropic effort / thinking 設定 (破壊的変更)**: `AnthropicGenerateContentConfig` を新設し `effort` (low/medium/high/xhigh/max) を直接指定可能に。 thinking/effort 有効時は sampling パラメータ (temperature/top_p/top_k) を自動除外し Anthropic API 400 を回避。 従来 Claude で無視されていた temperature/top_p/top_k/stop_sequences/max_output_tokens が client へ伝播するようになり、 `max_output_tokens` が既定 max_tokens=8192 を上書きする (4c862b96)
- **LiteLLM 動的カスタムヘッダー**: `RunConfig.http_options` を追加し、 per-request の HTTP ヘッダー/timeout/retry を LiteLLM モデル層まで伝播 (000d74da)
- **ToolNode 入力緩和**: workflow の `ToolNode` が dict/None に加え JSON 文字列・`types.Content` を受理 (4e446324)
- **managed-agent の built-in tool 解決**: `LlmRequest.is_managed_agent` フラグを追加。 Gemini モデル未設定でも `google_search`/`url_context` がサーバー側 config を解決 (f11d19d2)
- **max_parallel_workers 公開**: `@workflow.node` デコレータおよび `Node` クラスで並列ワーカーの同時実行数を制御可能に (199d9548)
- **BigQuery Analytics プラグイン観測制御**: `BigQueryAgentAnalyticsPlugin` に otel 相関・`custom_metadata_allowlist`・`payload_column_denylist` を追加 (38d715cb)
- **environment_id の回復**: `LlmResponse.environment_id` を interactions ストリームから populate し、 ターン跨ぎで sandbox environment を再利用可能に (81f9f2ec)

**[Security / Hardening]**

- **MCP mTLS ヘッダー判定を case-insensitive 化**: httpx のヘッダーキー小文字正規化に合わせ authorization ヘッダー検査を大文字小文字非依存に (38700324)
- **ApplicationIntegrationTool の mTLS エンドポイント動的解決**: ハードコード URL を `_mtls_utils.get_api_endpoint` 経由に置換し client 証明書提示時に `.mtls.googleapis.com` variant を使用 (37ca6fbe)
- **Secret/Parameter Manager client の auth_token 初期化復元** (46a21817)
- **GitHub Actions を main/v1 ブランチ・main リポジトリに限定**: fork 上での workflow 実行と merge block を抑止 (8c4173ee)
- **CI の JSON 受け渡し硬化**: inline heredoc を環境変数経由に変更し script injection を防止 (8c7fcd1c)

**[修正]**

- **custom Gemini 接続ロジックを全 3_x モデルへ**: 3.1 限定だった処理を 3_x 系全体に適用 (8aff5141)
- **DeepSeek-V3 独自 inline tool-call トークンのパース**: LiteLLM が structured `tool_calls` に変換しない場合の fallback を追加 (c5b2caad)
- **空 STOP ターンをエラー化**: 非ストリーミング時、 finish_reason=STOP かつ content 無しを `MODEL_RETURNED_NO_CONTENT` エラーイベントとして surface (932a9b56)
- **perf: LLM リクエスト構築時の session contents deepcopy 回避**: `_get_contents` の全イベント deepcopy を除去（プロファイル上 ~30s run のうち ~4-7s を占める非 LLM CPU sink） (400f512d)
- **refactor: dynamic scheduler 系**: static graph dispatch を dynamic scheduler へ rebase (196f7708)、 transfer loop を抽出 (7329f7d3)

#### 2026-06-27 新着 (v2.3.0 後の未リリース開発: streaming deltas / OpenAI Responses labs / sandbox hardening)

main HEAD が `50c81ebf` まで進行（v2.3.0 後 81 commits、 新リリースタグ未付与）。 Copybara export のため commit subject に `#PR` は付与されず、 short hash で参照する。 主要なもの:

**[Features]**

- **Interactions streaming deltas**: thought / media / code-exec / function-result デルタを stream (b2dda6e)、 streamed grounding + final usage metadata を surface (6a50b8d)
- **OpenAI Responses API サポート (labs)** (6b831d5)
- **provider-prefixed Gemini model ID サポート** (816a87f)
- **Vertex AI session TTL / expiration サポート** (49d4441)
- **Vertex AI memory `load_profiles` tool** (fb2b3af)、 `VertexAiMemoryBankService.search_memory` のエラーハンドリング (f3529e9)
- **DiscoveryEngineSearchTool の mTLS サポート** (8ba0e6a)
- **Skills state injection**: `adk_inject_state` で session state を `SKILL.md` に注入 (3afdb08)
- **ADK CLI dev server リファクタ**: dev mode での nested agents サポートと API 簡素化 (35a3e4c)
- **MCP HTTP traces**: server request / error の trace 追加 (4c4f77a)
- **Context に `branch` property を露出** (50c81ef)

**[Security / Hardening]**

- **AgentTool `config_path` 解決の path traversal 防止** (171ae9e)
- **ContainerCodeExecutor sandbox をデフォルト hardening** (0a9ce0f)
- **YAML agent-config code reference の module blocklist** (6a5be34)
- **`adk web` 下ロード時に agent-config args denylist を強制** (e506fa6)

**[修正]**

- **Vertex AI Live API session replay 修正**: reconnect / modality switch で replay (c007a87)
- **Anthropic thinking blocks + signature を LiteLLM round-trip で保持** (febb250)、 streamed reasoning delta 保持 (b9625bf)
- **AgentRegistry base URL を v1alpha → v1 へ移行** (82432a3)
- **google-genai 2.9 SDK 対応**: interactions 変換を適応 (9f3aeef)、 **MariaDB で tzinfo strip** (2f799d5)

#### 2026-06-19 新着 (v2.3.0 マージ / Template Injection 修正 SECURITY / A2A serialize 修正群 / tuple tool params)

- **v2.3.0 を main にマージ** (`chore: merge release v2.3.0 to main`): 2.x 系の次期リリース
- **SECURITY: Filename 経由の Code Generation Template Injection 修正** (`fix: Fix Code Generation Template Injection via Filenames`): ファイル名を介したテンプレートインジェクションを遮断
- **A2A `_serialize_value()` 修正群**: JSON-native コンテナへ再帰 (`recurse into JSON-native containers`)、 JSON-native 型を保持 (`preserve JSON-native types`)
- **tool tracing: `safe_json_serialize` で Pydantic モデルを処理** (`fix: handle Pydantic models in safe_json_serialize`)
- **feat(tools): tuple tool parameters サポート**: ツールパラメータに tuple 型を許可
- **LiteLLM Claude thinking blocks 修正**: `display: "omitted"` の thinking blocks が失われる不具合を修正
- **`RunConfig.response_modalities` に Modality enum を使用**
- **feat: GcsArtifactService で `file_data` URI 参照をサポート**
- **instructions_utils 修正群**: placeholder matching の regression 修正、 invalid な nested path のマッチング修正、 internal customers を壊す instruction util リファクタを rollback
- **adk deploy で ignore ファイルを尊重** (`fix(cli): respect ignore files in adk deploy commands`)
- **create_session で MySQL 向けに datetime の tzinfo を除去**、 **node runtime で `run_config` の custom_metadata を user event に適用**

**注目**: v2.0.0 GA（2026-05-19）後、 **v2.1.0 → v2.2.0（2026-06-04）と 2.x 系リリースが軌道に乗った**。 v2.2.0 は **Google GenAI SDK v2.0.0 対応**、 **AutoTracingPlugin（OpenTelemetry 自動計装）**、 **RubricBasedMultiTurnTrajectoryEvaluator**、 native OTel `gen_ai.client.*` metrics など observability / eval 強化が柱で、 セキュリティ修正も多い（下記）。 LTS 側も **v1.35.0（2026-06-10）** がリリースされ、 Gemini 3.1 Live 系の修正（input transcription の扱い、 grounding metadata デフォルト、 history config injection）を backport。 v2.2.0 後の main では **E2BEnvironment（リモート sandbox workspace）**、 **GEPARootAgentOptimizer**、 BigQuery Agent Analytics plugin の ADK 2.0 producer cut、 `GOOGLE_GENAI_USE_ENTERPRISE` env var などが進行中。

#### 2026-06-18 新着 (Gemma4 / cached token counts / DatabaseSessionService AsyncEngine 再利用 / Live 安定化)

main の HEAD が `73ecf8d7` まで進行（前回記録から多数 commit）。 主要なもの:

**[Features]**

- **Gemma4 を Gemini でサポート** (`feat(gemma4)`): Gemma4 モデルを Gemini クラスで利用可能に
- **Gemini クラスに configuration options 追加** (`feat(models)`): Gemini クラスの設定オプションを拡充
- **DatabaseSessionService の AsyncEngine 再利用**: 既存の SQLAlchemy `AsyncEngine` を再利用可能に、 eager 初期化用の public `prepare_tables()` を追加
- **cached token counts の報告**: Anthropic / OpenAI モデルの cached token count を report、 `ContextCacheConfig` に cache 作成 timeout 用の `create_http_options` 追加
- **Live function response の挙動制御**: `response_scheduling` を追加 (`feat(tools)`)
- **template injection で nested state access サポート** (`feat(utils)`)、 **`@node` decorator に `parameter_binding` を露出**
- **eval**: `generate_responses` で `user_simulator_config` を露出、 `adk run` CLI に `log_level` option 追加
- **invocation_id を `_setup_invocation_context` に渡す**

**[Security / Hardening]**

- **ReDoS 防止**: code block 抽出での ReDoS を防止 (`fix: prevent ReDoS in code block extraction`)
- **auth: client-credentials scopes 欠落の安全処理**: missing client-credentials scopes を安全にハンドリング
- **CLI: 生成 `.env` ファイルの operator safety 改善**

**[修正]**

- **Live 系安定化**: 1011 error での reconnect、 thinking config の forward、 Vertex / Enterprise Live session での history_config rejection、 trace serialization から live HTTP clients を除外、 runner の live event buffering 削除、 Live API `server_content` からの grounding_metadata 抽出
- **sessions**: asyncpg で `append_event` 後の MissingGreenlet 防止、 DatabaseSessionService の追加修正、 Agent Engine が short session ID でなく full resource name を渡す際の vertex_ai_session_service クラッシュ修正
- **a2a**: Vertex AI mode で part_metadata を抑制、 prompt が data part にある場合の HITL interrupt レンダリング、 final events での execution metadata 保持、 Message.role を正しい GenAI content role にマップ
- **artifacts**: `GcsArtifactService` load で `.text` を保持、 空の GCS text artifact を保持、 `LoadArtifactsTool` で image/svg+xml を text に変換
- **models / planners**: STOP + 空 content 時にエラーを surface、 litellm の function call id 保持、 union 型 schema の sanitize、 leading parallel function calls を全保持、 `BuiltInPlanner` subclass の `process_planning_response` override 許可、 `MALFORMED_FUNCTION_CALL` を surface し `on_model_error` で recover 可能に
- **その他**: transfer target が sibling agent か検証、 `before_agent_callback` short-circuit 時に `output_key` を persist、 VertexAiRagRetrieval の event loop block 防止、 firestore session state を JSON serialize、 grounding metadata の propagate、 isolation_scope 伝播による history filtering ループ防止
- **otel**: stable / experimental semconv logs 構築用の pure functions 追加、 MCP toolset との telemetry functional test 追加

#### 2026-06-15 新着 (compaction function response 修正)

- **compaction が function response を orphan 化する問題を修正**: compaction によって function response が孤立する不具合を修正（会話履歴の整合性保持）
- **CI: kokoro pre-commit presubmit に addlicense tool を install**

#### 2026-06-13 新着 (enterprise パラメータ移行 / mTLS / Agent Identity / Antigravity wrapper)

main の HEAD が `ca8baf19...d3c21d71` の 67 commits 進行。 主要なもの:

**[Features]**

- **enterprise パラメータへ移行**: core と CLI を enterprise parameters へ移行、 samples / docs の `vertexai` 呼称を `enterprise` に置換、 `GOOGLE_GENAI_USE_ENTERPRISE` env var 系の整備
- **mTLS サポート**: `McpToolset` を `AsyncAuthorizedSession` へ移行して mTLS 対応、 `AgentRegistry` client にも mTLS 追加
- **Agent Identity auth provider**: Agent Identity Credentials service ベースの auth provider 実装、 auth provider resource name に基づく diversion ロジック、 `gcp_auth` client UI を Remote Agents 対応に
- **Antigravity SDK agent wrapper (実験的)**: labs に experimental な Antigravity SDK agent wrapper を追加
- **GCS first-party toolset**: ADK integrations に GCS の first-party toolset を追加
- **Live API 強化**: `RunConfig` で Live API translation config をサポート、 live usage metadata で output token count を伝播、 Gemini 3.1 live は各ターン末尾でのみ grounding_metadata を送信
- **per-request OpenTelemetry 設定**: telemetry をリクエスト単位で構成可能に
- **`load_web_page` に request timeout 追加**
- **default model を gemini-3.5-flash に更新** (samples 含む)

**[破壊的/挙動変更]**

- **telemetry metrics の単位を ms → 秒へ**: agent / tool 実行時間メトリクスをミリ秒から秒に変更（既存ダッシュボード要確認）
- **otel google-genai instrumentor >=0.7b1 を要求**: genai 2.x 向けに instrumentor 下限を引き上げ
- **`a2a` を agent_engine デプロイの必須依存に**、 **`google-cloud-parametermanager` を optional 依存へ移動**

**[修正]**

- **workflow 系の安定化**: replay divergence hang / sequence barrier の防止、 shared `InvocationContext` の branch mutation 防止、 conditional route 未マッチ時の silent dead end 修正、 explicit single-turn contents の保持、 routed nodes の silent drain 防止
- **`InMemoryMemoryService` 検索の非Latin テキスト対応**
- **CI セキュリティ硬化**: fork での workflow 実行を防ぐ repository check 追加、 pr-triage secrets を same-repository `pull_request_target` に gate、 release analyzer workflow input の shell 補間を停止
- **ruff で unused-import enforcement を採用**

#### v2.2.0 の主要な変更点（2026-06-04）

**[Security / 重要修正]**

- **Agent Builder file tools の path traversal ブロック** / **GCS skill 展開の Zip Slip 修正** / **v0 actions blob の unpickle 制限** / **`delete_session` の session 所有権検証** — エージェント実行系の防御強化
- **CVE-2026-48710 対応**: starlette / fastapi を bump

**[Features]**

- **AutoTracingPlugin**: OpenTelemetry 自動計装プラグイン
- **RubricBasedMultiTurnTrajectoryEvaluator**: ルーブリックベースのマルチターン軌跡評価
- **A2A 連携強化**: `to_a2a(Workflow)` 対応、 A2A message metadata の保持、 input-required vs auth-required の区別
- **`BaseSessionService.get_user_state(app_name, user_id)`** 追加、 **compaction summary に thoughts / tool calls を含める**

#### v1.34.0 / v2.0.0 GA 後の変更点（大半は v2.2.0 に取り込み済み）

**[運用 / アーキテクチャ]**

- **v2 リリースワークフローを v1 ブランチへ repoint**: v2 release workflows と manifests を v1 ブランチに付け替え、 main → v2 自動 sync workflow を削除（v1 ライン主導への運用転換）
- **Google GenAI SDK v2.0.0 対応**: Interactions で ADK を Google GenAI SDK v2.0.0 に対応
- **デフォルトモデル gemini-3-flash-preview 化**: agents のデフォルトモデルを gemini-3-flash-preview に変更（サンプル含む）
- **1.x agent config wiring 復元**: 後方互換のため 1.x agent config wiring を restore

**[Features]**

- **`request_input` tool 標準化**: LLM による能動的な確認のための request_input tool を標準化
- **Live `turn_complete_reason` サポート**: Live responses で turn_complete_reason を保持し safety 情報をキャプチャ
- **native OTel `gen_ai.client.*` metrics**: gen_ai.client.* メトリクスをネイティブ emit
- **`custom_metadata` 伝搬**: run requests の custom_metadata を run config へ転送
- **sandbox templates / snapshots からの生成**: template / snapshot から sandbox を作成可能に
- **data agent チャート生成 / artifact ロード**: data agent にチャート生成と artifact loading を追加
- **telemetry 拡充**: gen_ai.user.message log records への user.id 付与、 tool call エラーのテレメトリ修正、 transcription event order の保持
- **skills 系**: adk-review skill / adk-issue skill 追加、 PR triage と CLA verification の自動化、 SkillToolset の experimental タグ削除
- **api_server クライアント切断時 abort**: client drop 時に run を abort してリーク防止

**[Security / Hardening]**

- **ReadFileTool コマンドの shell escape**: ReadFileTool コマンドで path と range を shell escape（セキュリティ）
- **OAuth2 token requests の scope 省略**: auth の OAuth2 token request から scope を omit
- **non-mTLS hardcoded endpoints チェック**: check-file-contents.yml で非 mTLS の hardcoded endpoint を検出

**[Bug Fixes]**

- **MCP 初期化ハング / task group leak 防止**: MCP の initialization hang と task group leak を防止、 MCP tool エラー時の session drop も防止
- **Gemini 3.1 grounding metadata 損失防止**: Gemini 3.1 (live 含む) の grounding metadata の silent drop / transcription finished events を修正
- **graph chat agent wiring 修正**: graphs で chat agent の誤った wiring を防止
- **LoadSkillResourceTool 無限リトライ停止**: RESOURCE_NOT_FOUND 時の無限リトライループを停止
- **AgentTool sub-Runner plugin 修正**: AgentTool の sub-Runner で親の plugins を close しない、 prefix 設定時の skill tool 参照破損防止 + tool_filter サポート
- **state / live 修正**: NodeRunner path での state_delta 保持、 live session 再接続時の transparent config 保持
- **循環 import 解消**: base_tool / llm_request の循環 import 解消、 GCS evaluation managers / google-cloud-storage の遅延 import 化
- **perf(flows)**: agent tool unions の並列解決

#### v2.0.0 GA の主要な変更点（2026-05-19）

- **General Availability 到達**: multi-agent workflow と dynamic agent collaboration の production-grade foundations 確立
- **Multi-Agent Workflow Engine**:
  - **Flexible Execution Graphs**: 非線形・条件分岐・サイクリックなエージェント実行パターンを model-agnostic に編成するエンジン
  - **Intelligent Task Delegation**: 並列 sub-agent workers、 nested 階層チーム構成、 resilient な dynamic scheduling を有効にするモジュラー workflow abstraction
- **Dynamic Agent Collaboration**:
  - **Native Inter-Agent Routing**: inter-agent messaging、 control state handoffs、 context variable propagation を multi-agent flow 間でシームレスに編成
- **v2.0.0 alpha/beta パイプライン経由**: v2.0.0a1 → v2.0.0a2 → v2.0.0a3 → v2.0.0b1 → v2.0.0 GA という段階リリース。 main ブランチを v2.0.0 GA へ切り替え（v2 への transition）。

#### v1.34.0 の主要な変更点（2026-05-18）

**[Features]**

- **a2a persistent task stores サポート**: a2a に persistent task store サポートを追加 (cd78d87)
- **Gemini Live API in ADK evaluate**: ADK evaluate に Gemini Live API のサポートを追加、 evaluation_generator で `Runner.run_live()` を利用、 local / base eval service の live mode 対応 (790c9be)
- **mTLS Google Cloud Telemetry exporter**: Google Cloud Telemetry exporter に mTLS サポート (cfe8d2c)
- **A2aAgentExecutor factory in `to_a2a()`**: `to_a2a()` 関数に factory を渡せるよう拡張 (115124c)
- **non-ADK input-required events サポート**: ADK 外で生成された input-required events をサポート (6e53472)
- **user simulator conv history config**: user simulator に渡す会話履歴に tool calls/responses を含めるか設定可能化 (baf7efb)
- **GCPSkillRegistry 実装**: ADK に `GCPSkillRegistry` を実装 (88ebd42)
- **Skill Registry 実装**: ADK に Skill Registry を実装 (380d261)
- **Agent Skill description validation 改善**: validation メッセージを informative 化 (9f38973)
- **ask_data_agent / ask_data_insights データ取得簡素化**: data retrieval ハンドリングを簡素化 (48f1b30)
- **McpToolset OAuth PKCE サポート**: McpToolset で OAuth PKCE をサポート (e7316dc)
- **CI: Gemini auto review/invoke workflows**: Gemini ベースの自動レビュー / invoke ワークフローを CI に追加 (fd8b492)

**[Bug Fixes]**

- **output_key state delta callback 可視性修正**: agents の output_key state delta を callback で見えるよう修正 (0524797)
- **Anthropic negative thinking_budget → adaptive thinking**: 負の thinking_budget を adaptive thinking にマッピング (03b915b)
- **refreshed OAuth2 credentials persist**: auth で refresh された OAuth2 credentials を store に永続化 (218ea76, #5329)
- **不要 OAuth フロー削除**: auth から不要な OAuth flows を削除 (c35a579)
- **Interactions API double-escape 防止**: dict 値の pre-serialization を回避 (85f397d)
- **CacheMetadata active-state invariant 強制 + fingerprint-only metadata 対応**: cache active state invariant を強制し、 performance analyzer で fingerprint-only metadata をハンドリング (76b9f0b, 9c5de58)
- **AnthropicLlm import OSError catch**: AnthropicLlm import 時の OSError を捕捉 (91cb5c6)
- **project_id fallback**: credentials に quota project が無い場合 project id にフォールバック (e377cb5)
- **SkillToolset dynamically loaded tools 修正**: 同一 invocation 内で SkillToolset に dynamically load された tool が見つからない問題を修正 (f9097cb)
- **sub live agent session resumption handle 分離**: sub live agent が parent から session resumption handle を継承して会話を中断する問題を修正 (8dd9147)
- **Anthropic tool_result blocks string content 保持**: Anthropic models の tool_result blocks で string content を保持 (9a1e75f, #5358)
- **Anthropic session resume で tool_use ID 保持**: Anthropic models の session resume で tool_use ID を保持 (327c45f, #5074)
- **空 GenerateContentResponse の正常扱い**: prompt feedback の無い empty GenerateContentResponse を成功として扱う (0cb9ae9)
- **AgentTool 結果保持**: `code_execution_result` と `executable_code` を AgentTool 内で保持 (7e61b51, #5481)
- **A2A 変換時 role 尊重**: events を A2A 形式に変換する際に user / agent role を区別 (59f7347)
- **AgentRegistry import eager raise**: a2a-sdk 不在時に AgentRegistry import で eagerly に raise (33cf6cb)
- **AnyIO CancelScope task boundary violations 防止**: MCP セッション作成失敗時の CancelScope violations を防止 (4309159)
- **HITL イベントの compaction 抑止**: Human-in-the-Loop に関わる events の compaction を防止 (bb2efb6)
- **live_session_id 保持**: function call ハンドリング時に live_session_id を保持 (07a9a01)
- **trace 含まれない場合 llm_response シリアライズ抑止**: trace に含まれない時のみ llm_response を json シリアライズ (1284493)
- **CLI deprecated フラグ＆ version-based service URI 削除**: CLI の deprecated flag と version-based service URI handling を削除 (e04a468)
- **gemini-3-flash-preview モデル更新**: hello world / session state agent サンプルのモデル更新 (6d89d21, 2d423e8)
- **gemma4 LiteLLM tool_responses role 使用**: gemma4 models で LiteLLM integration の tool_responses role を使用 (3d07960, #5650)

**[Performance]**

- **lazy-load サービスレジストリ**: `apps.app` を分割し service registry を lazy-load、 cold start を約 8% 削減 (bd062ec)
- **isEnabledFor で debug log evaluation ガード**: debug log evaluation を isEnabledFor でガード (57d8fc7)
- **find_context_parameter introspection キャッシュ** (ec54bd4)

**[Code Refactoring]**

- **`a2a_metadata` 定数化**: extension 開発者が依存できるよう `a2a_metadata` 文字列を定数化 (0821f2d)

#### v1.33.0 後の変更点（v1.34.0 へ取り込まれた hotfix を含む）

- **Gemini Live API 評価対応**: ADK evaluate に Live API サポート、 `Runner.run_live()` を evaluation_generator で利用、 local / base eval service の live mode 対応
- **GCPSkillRegistry 実装**: ADK に `GCPSkillRegistry` を新規実装
- **mTLS Telemetry exporter**: Google Cloud Telemetry exporter に mTLS サポート追加
- **A2aAgentExecutor factory in to_a2a()**: `to_a2a()` に factory を渡せるよう拡張
- **SkillToolset 安定化**: SkillToolset から experimental タグ削除
- **lazy-load サービスレジストリ**: `apps.app` を分割し service registry を lazy-load、 cold start を約 8% 削減 (perf)
- **AgentTool 結果保持**: `code_execution_result` / `executable_code` を AgentTool 内で保持
- **A2A 変換時 role 尊重**: events を A2A 形式に変換する際に user / agent role を区別
- **OAuth フロー整理**: 不要な OAuth フローを auth から削除 (c35a5796)
- **CLI deprecated フラグ＆ service URI 削除**: 廃止された CLI flag と version-based service URI handling を削除 (e04a4683)
- **SkillToolset dynamically loaded tools 修正**: 同一 invocation 内で SkillToolset に dynamically load された tool が見つからない問題を修正 (f9097cbf)
- **project_id fallback**: credentials に quota project が無い場合 project id にフォールバック (e377cb5e)
- **non-ADK input-required events 対応**: ADK 外部で生成された input-required event をサポート (6e534723)
- **Gemini auto review/invoke workflows**: CI に Gemini ベースの自動レビュー / invoke ワークフローを追加 (fd8b4929)
- **Anthropic session resume tool_use ID 保持**: session resume 時に Anthropic モデルの tool_use ID を保持 (327c45f9)
- **Skill Registry 実装**: ADK に Skill Registry を実装 (380d261e)
- **a2a persistent task stores サポート**: a2a に persistent task store サポート追加 (cd78d87b)
- **CacheMetadata active-state invariant 強制**: cache の active-state invariant を強制 (76b9f0ba)
- **sub live agent session resumption handle 分離**: sub live agent が parent から session resumption handle を継承して会話を中断する問題を修正 (b4dab9a)
- **refreshed OAuth2 credentials 永続化**: refresh された OAuth2 credentials を store に persist (af74b21)
- **gemini-3-flash-preview モデル更新**: hello world / session state agent サンプルのモデルを更新
- **AgentRegistry 即時エラー**: a2a-sdk 不在時に AgentRegistry import で eagerly に raise
- **`a2a_metadata` 定数化**: extension 開発者が依存できるよう `a2a_metadata` 文字列を定数化
- **CacheMetadata fingerprint-only 対応**: performance analyzer で fingerprint-only metadata を扱う
- **AnthropicLlm import OSError catch**: AnthropicLlm import 時の OSError を捕捉
- **McpToolset OAuth PKCE サポート**: McpToolset で OAuth PKCE をサポート

#### v1.33.0 の主要な変更点（2026-05-08）

**[Features]**

- **BufferableSessionService**: バッファリング可能なセッションサービスを新規追加 (0bc767e)
- **LlmResponse function call/response ヘルパー**: `get_function_calls()` と `get_function_responses()` を LlmResponse に追加 (22fae7e)
- **ApigeeLlm credential 注入**: ApigeeLlm に credentials を inject できるオプション追加 (ce578ff)
- **ADK environment tools truncation 設定化**: environment tools の truncation limit を設定可能化 (83ae405)

**[Bug Fixes]**

- **video inline data session 除外**: inline data の video event をセッションに保存しないようフィルタ (88421f8)
- **fork detection / offload limits / response logging (BigQuery)**: BigQuery plugin の fork 検出、 offload limit、 response logging 修正 (9d1bb4b)
- **hot reload agents for adk web**: adk web で agent の hot reload に対応 (740557c)
- **state_delta overwrite skip on function_response-only**: function_response-only event での state_delta 上書きをスキップ (fc27203, 211e2ce)
- **CustomAuthScheme 未登録エラー明確化**: AuthProvider 未登録時に actionable error を投げる (83f9817)
- **`req.app_name` → `app_name` 修正**: 正しい変数名へ修正 (8286066)
- **LlmBackedUserSimulator 空応答エラー**: 空応答時に明示的エラーメッセージを出す (fb92aad)
- **agent engine デプロイ認証**: API key ではなく project / location を使用 (398f28f)
- **catch genai.ClientError sandbox 不在時**: sandbox 不在時の genai.ClientError を catch (69fa777)
- **`asyncio.sleep` 化**: blocking sleep を asyncio.sleep に置換しイベントループブロックを回避 (3a1eadc)
- **ListSkillsTool 重複防止**: ListSkillsTool 利用可能時に skills を system instruction に追記しない (01f1fc9)
- **double append bug 修正**: double append バグを修正 (f8b4c59)
- **Express mode API call default api key**: Express mode API call で default api key param を含める (e833995)

**[Code Refactoring]**

- **adk metrics の input.type/output.type 属性削除**: metrics 定義の整理 (9559968)
- **workflow.steps メトリクス計算調整**: `workflow.steps` 計算ロジックを調整＋ unit test 追加 (03d6208)

#### v1.32.0 の主要な変更点（2026-04-30）

**[Security]**

- **`load_web_page` SSRF / local-file アクセス修正**: load_web_page における SSRF とローカルファイルアクセス脆弱性修正 (0447e93)
- **nested YAML configs RCE 修正**: ADK のネスト YAML 設定経由 RCE 脆弱性ブロック (74f235b)
- **PubSub / Eventarc user_id sanitization**: PubSub サブスクリプション / Eventarc source 由来の user_id をサニタイズ (#5324, 0c4f157)
- **credential isolation in auth context**: 解決済み認証情報の context 内分離（race condition / データ漏洩防止） (5578772)
- **litellm cap >= 1.83.7**: CVE パッチを取り込むため litellm の最低バージョンを引き上げ (6d2ada8)
- **Vertex RAG memory display name スコープ化**: scope 化 (784350d)

**[Core / Features]**

- **Anthropic thinking blocks サポート**: Anthropic の thinking blocks フォーマット対応 (16952bd)
- **adk deploy CLI express mode onboarding**: adk deploy CLI に express mode オンボーディング追加 (2b04996)
- **native OpenTelemetry agentic metrics**: ネイティブ OpenTelemetry agentic メトリクス追加 (6942aac)
- **event compaction OpenTelemetry tracing**: event compaction の OpenTelemetry tracing 追加 (c65dd55)
- **GcpAuthProvider 2LO/3LO/API Key sample**: GcpAuthProvider 経由の 2LO/3LO/API Key auth サンプル追加 (909a8c2)
- **ComputerUseToolset predefined function exclusion**: 事前定義関数の除外サポート (d760037)
- **BigQueryAgentAnalyticsPlugin credentials**: credentials パラメータ追加 (34713fb)
- **Apigee LLM refusal messages**: Apigee LLM での refusal メッセージ対応 (d6594a1)
- **`save_live_blob` パラメータ**: /run_live エンドポイントに save_live_blob クエリパラメータ追加 (36ab8f1)
- **MCP tool エラー/transport graceful handling**: ツール実行エラー・トランスポートクラッシュを安全に処理 (7744cfe)
- **McpToolset credential_key 指定**: ユーザー定義の credential_key 対応 (282db87, #5103)
- **SaveFilesAsArtifactsPlugin reference 抑止オプション**: メッセージにリファレンスファイルを attach させないオプション (987c809)
- **BigQuery LLM cache メタデータロギング**: LLM cache メタデータを BigQuery に記録 (02deeb9)
- **rubric-based eval `evaluate_full_response`**: full response 評価オプション (#5316, 7623ff1)

**[Bug Fixes]**

- **state_delta マージ時 list アキュムレート**: 並列ツール呼び出しの state_delta マージで list 値を accumulate (#5190)
- **GcpAuthProvider Bearer scheme 大文字化**: capitalized Bearer に修正 (ad937fe)
- **load_web_page 修正、google-genai 下限 bump**
- **LoopAgent サブエージェント state リセット防止**: pause 時に sub-agent state をリセットしない (8846be5)
- **VertexAiSessionService list filters quote 修正**: `user_id` リテラル quote 修正 (bdece00)
- **safe-JSON serializer ValueError 捕捉**: 循環参照時の ValueError ハンドリング (#5412, 70a7add)
- **bound token mcp_tool 無効化** / **web oauth flow と trace view 修正** / **schema RecursionError 修正**
- **ReflectRetryToolPlugin 例外順序修正** / **mcp 最低バージョン 1.24.0 → 1.25.0 系**

**[Performance]**

- **lazy-load optional providers**: 任意 provider と auth chain の lazy-load によりコールドスタート約 25% 改善 (66bfedc)

#### v1.31.1 / v1.31.0 の主要な変更点

**[Core]**

- **Parameter Manager / Secret Manager ユーザーエージェント**: Google ユーザーエージェント追加
- **VertexAiMemoryBankService `memories.ingest_events`**: サポート追加
- **Vertex AI Agent Engine Sandbox 統合**: コンピュータユースサポート
- **Firestore サポート追加**
- **Live session_id in LlmResponse**: LlmResponse に live session_id 追加
- **MCP 最低バージョン 1.24.0**: MCP 最低バージョンを 1.23.0 → 1.24.0 へ引き上げ

**[Bug Fixes]**

- **CLI コンソール URL パス修正**: CLI 展開後のコンソール URL パス修正 (#5336)
- **on_event_callback 順序修正**: イベント処理順序のバグ修正 (#3990)
- **FunctionDeclaration json_schema フォールバック**
- **BigQuery プラグイン問題解決**

#### v1.30.0 の主要な変更点

**[Core]**

- **Auth Provider サポート**: Agent Registry への Auth Provider サポート追加
- **Parameter Manager 統合**: ADK に Parameter Manager 統合追加
- **Gemma 4 モデルサポート**: ADK での Gemma 4 モデルサポート (#5156)
- **Live avatar サポート**: ADK での Live avatar サポート
- **Live session resumption**: BaseLlmFlow で `live_session_resumption_update` を Event として公開 (#4357)
- **BigQuery ツール Stable 昇格**: BigQuery ツールを安定版に昇格
- **A2A アーティファクトインターセプター**: `RemoteA2aAgent` でインターセプターを使用したアーティファクト含有 A2A イベント送信

**[Security]**

- **credential 漏洩脆弱性修正**: Agent Registry での credential 漏洩脆弱性修正
- **path traversal バリデーション**: user_id と session_id に対するパストラバーサル検証 (#5110)

#### v1.29.0 の主要な変更点

**[Core]**

- **EnvironmentToolset**: ファイル I/O とコマンド実行のための EnvironmentToolset 追加
- **LocalEnvironment**: ローカルコマンド実行とファイル I/O のための LocalEnvironment 追加
- **Easy GCP サポート**: ADK CLI に Easy GCP サポート追加
- **Secret Manager リージョナルエンドポイント**: `SecretManagerClient` のリージョナルエンドポイントサポート
- **Auth Provider 登録 API**: Credential Manager にカスタム Auth Provider 登録のパブリック API 追加
- **MCP ツール追加 HTTP ヘッダー**: MCP ツールでの追加 HTTP ヘッダーサポート

**[Tools]**

- **BashTool シェルメタキャラクターブロック**: BashTool でシェルメタキャラクターのブロック機能追加
- **BashTool リソースリミット**: サブプロセスの設定可能なリソースリミット
- **BashTool プロセスグループ管理**: 堅牢なプロセスグループ管理とタイムアウト
- **BigQuery ADK 1P Skills**: BigQuery ツールセットに ADK 1P Skills 追加

**[Models]**

- **Vertex AI カスタムセッション ID**: Vertex AI Session Service でのカスタムセッション ID サポート
- **Model endpoints in Agent Registry**: Agent Registry でのモデルエンドポイントサポート

**[Optimization]**

- **コンテキスト伝播**: スレッドプールへのコンテキスト伝播
- **InMemorySessionService 浅いコピー**: オプションの浅いコピーセッション

**[Bug Fixes]**

- **BigQuery analytics credential 秘匿**: BigQuery analytics プラグインでの credential 秘匿
- **BaseToolset.get_tools() キャッシュ**: 同一呼び出し内での get_tools() キャッシュ
- **pending function call コンパクション防止**: pending function call を持つイベントのコンパクション防止 (#4740)
- **Live session resumption/GoAway ハンドリング**: Live セッション再開と GoAway シグナルの処理 (#4996)

#### v1.28.0 の主要な変更点

- **A2A lifespan パラメータ**: A2A lifespan パラメータサポート追加
- **BigQuery 1P Toolset 移行**: BigQuery 1P ツールセットの移行
- **Spanner Admin Toolset**: Spanner Admin ツールセット新規追加
- **Slack 統合**: Slack インテグレーション追加
- **SSE ストリーミング**: 適合テスト向け SSE ストリーミングサポート
- **Anthropic thinking_blocks**: LiteLLM での Anthropic thinking_blocks フォーマットサポート
- **MCP サンプリングコールバック**: MCP サンプリングコールバックサポート
- **モジュールインポート保護**: 任意モジュールインポートに対する保護追加（セキュリティ）

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| credential manager が `tool_context` を受け取るよう変更 (v1.24.0) | `callback_context` から `tool_context` への引数変更 |
| SecretManagerClient パッケージ移動 (v1.29.0) | `google.adk.integrations.secret_manager` パッケージへの移動 |

#### 参考リンク

- [ADK Python](https://github.com/google/adk-python)

---

### ADK Go

**現行バージョン**: **v2.0.0 (2026-06-30)**（直前に v1.5.0 も同日リリース。 1.x は `v1` ブランチで継続メンテ）

**チェックアウト状態**: `v2.0.0-24-g020d941` (v2.0.0 + 24 commits、 HEAD 2026-07-17。 新タグ未発行)

#### 2026-07-18時点 新着 (v2.0.0 後 24 commits: agentregistry / provider auth / MCP per-request auth)

- **`agentregistry` package**: discovery / REST transport / RemoteAgent + McpToolset factory を追加 (#1122–#1148)
- **credential/provider auth**: core の credential/provider auth package を新設、 MCP toolset の per-request auth に対応
- **参考**: v2.0.0 (2026-06-30) 本体は Multi-Agent Workflow エンジン GA (#1109、 v1.5.0→v2.0.0 で 548 files/+51k 行)。 adk-python 2.0 と同一の workflow GA テーマ

**注記**: 単一モジュール repo（monorepo の multi-module タグではない）。 `v2.0.0` は Go major の import path bump (`google.golang.org/adk` → `/v2`) を伴う正式メジャーリリース。 親 submodule の `git describe`（フラグなし）が `v0.1.0-255-g0f5cfa0` と表示するのは **annotated タグのみを対象にする既定挙動**が原因（タグ未 fetch ではない）。 この repo で annotated タグは `v0.1.0` の1本のみで、 v1.0.0〜v2.0.0（v1.4.0/v1.5.0 含む）は全て lightweight タグ。 `git describe --tags`（lightweight 込み）なら正しく `v2.0.0-2-g0f5cfa0` に解決する。

**注目**: **ADK Go 2.0 メジャーリリース (2026-06-30)**。 `workflow` パッケージ新規導入（scheduler ベースの goroutine-per-node 実行エンジン、 HITL の pause/resume・handoff/re-entry、 JoinNode fan-in 等）が柱で、 module path 変更・`session.NewEvent` の context 必須化・ToolContext/CallbackContext 統合など複数の破壊的 API 変更を伴う。 1.x 系は `v1` ブランチで継続メンテ。

#### 2026-07-09 新着 (agentregistry クライアント基盤の追加)

- **`agentregistry` パッケージを新規導入**: `Config`/`Client`/`New` のクライアント基盤と、 `agentregistry.googleapis.com` 向けの認証付き REST Transport を追加。 Application Default Credentials + mTLS エンドポイント選択、 typed `APIError`、 service wire types と list options、 resolution helper（`connectionURI`/`cleanName`/transport-binding map）を **adk-python から移植して behavioral parity を確保**。 list-response 型は AIP-158 の `ListXxxResponse` 命名に統一 (#1122)
- **test**: `TestA2ACleanupPropagation` を de-flake (#1131)

#### 2026-07-02〜2026-07-08 新着 (v2.0.0 後の未リリース開発: TaskRunner seam / LLM registry)

- **platform TaskRunner seam**: 呼び出し側制御の tool fan-out を可能にする実行 seam を追加 (#1050)
- **name-based LLM registry**: `Register` / `NewLLM` による名前ベースのモデル登録 (#1057)
- **`PackTool` を public API 化** (#1055)、 **runner に `NewInMemory` コンビニエンスコンストラクタ追加** (#1133)
- **tool-confirmation の整合**: confirmation リクエストを model-response 順で発行 (#1053)、 confirmation wrapper が下層 tool へ ProcessRequest を伝播するよう修正 (#1130)
- **fix**: 一時 state delta 除去時に入力 event を shallow copy し変更を防止 (#1128)

#### 2026-07-01 新着 (v2.0.0 ドキュメント整備・v1/v2 ブランチ運用)

- **contributing に v1/v2 ブランチ運用を明文化**: 2.0 リリースに伴い `main` を 2.x 開発線に、 `v1` を 1.x メンテ線として切り出し。 `main` の履歴は連続で古い clone は fast-forward 可、 1.x 修正は `origin/v1` 起点で行う旨を記載 (#1114 / 0f5cfa0)
- **workflow examples に per-example README とインデックス追加**: 新 workflow サブシステムのサンプル群にドキュメント整備 (#1113 / c478319)

#### 2026-06-30 新着 (ADK Go 2.0 メジャーリリース — workflow サブシステム導入)

- **ADK Go 2.0 リリース (v2.0.0、 破壊的変更)**: module path を `google.golang.org/adk` → `google.golang.org/adk/v2` へ変更。 547 files / +51,635・-7,030 の巨大 squash。 `workflow` パッケージを新規導入（scheduler ベースの goroutine-per-node 実行エンジン、 EdgeBuilder/NodeConfig、 グラフ検証、 HITL の pause/resume・handoff/re-entry モード、 JoinNode fan-in、 AgentNode、 retry config、 状態の session.State 永続化） (#1109 / 893e4a4)
- **`session.NewEvent` が `context.Context` 必須に (破壊的変更)**: シグネチャが `NewEvent(ctx, invocationID)` へ。 ID/timestamp を `platform` package 経由で取得（replay-safe 化）。 旧無ctx形式と暫定 `NewEventWithContext` は削除
- **ToolContext と CallbackContext を統一 Context に統合 (破壊的変更)**: 既存 mock は新規メソッド（`Actions`/`FunctionCallID`/`ToolConfirmation`/`RequestConfirmation`/`SearchMemory` 等）欠落でコンパイル不能に。 `agent.StrictContextMock` 埋め込みが推奨移行先（未 override メソッドは panic） (#945)
- **`agent.InvocationContext.TriggeredBy()` を削除 (破壊的変更)**: 未使用の public API 面を除去（`NodeState.TriggeredBy` フィールドは resume 用に存続） (#841)
- **v1.5.0 (1.x メンテ線最後の追加)**: VertexAiSessionService の FunctionCall/Response マッピングに table-driven test 追加 (#739 / caf798a)

| 変更 | 影響 |
|------|------|
| module path 変更 `google.golang.org/adk` → `/v2` (v2.0.0) | 全 import パスの書き換えが必要 |
| `session.NewEvent` が `context.Context` 必須化 (v2.0.0) | 呼び出しシグネチャ変更、 旧 `NewEventWithContext` 削除 |
| ToolContext / CallbackContext を統一 Context に統合 (v2.0.0, #945) | 既存 mock がコンパイル不能に。 `agent.StrictContextMock` へ移行推奨 |
| `agent.InvocationContext.TriggeredBy()` 削除 (v2.0.0, #841) | 該当 public API 利用箇所の書き換えが必要 |

#### 2026-06-24 新着 (conformance harness のみ)

- **conformance harness に `system_instruction` keyNode 処理を追加** (#1075): 適合テストハーネスで system_instruction の keyNode 処理に対応（test/conformance 層のみ、 API 変更なし）

#### 2026-06-19 新着 (load_memory VertexAiSessionService 互換 / context.Background 撤去 / linter)

- **built-in load_memory tool を VertexAiSessionService 互換に修正** (#793): VertexAiSessionService との組み合わせで動くよう load_memory を更新
- **context.Background の排除** (#1062): 全体で context.Background 利用を撤去し呼び出し元の context を伝播
- **linter 修正** (#1068): メインの linter 指摘を一括修正

#### 2026-06-18 新着 (Gemini Enterprise AgentSpace streams / manual session ID)

- **Gemini Enterprise AgentSpace streams サポート** (#777、 `fix(agentengine)`): agentengine で Gemini Enterprise AgentSpace の stream に対応
- **manual session ID 設定を許可** (#721): session ID の手動設定を可能に
- **`StrictContextMock` test double 追加** (#1019、 `feat(agent)`): テスト用の厳格な context mock を追加
- **AGENTS.md 追加** (#1045): AI coding agent 向けの AGENTS.md を追加

#### 2026-06-15 新着 (deterministic event creation seams)

- **platform clock / UUID provider seams 追加**: deterministic な event creation のため platform clock と UUID provider の差し替え seam を追加（テスト容易性向上） (#964)

#### 2026-06-10 新着 (govulncheck パッチ / Node 24 移行)

- **SECURITY: x/net と otel OTLP exporters を bump**: govulncheck advisory に対応するため `golang.org/x/net` と OTLP exporter 群をパッチ版へ (#994)
- **GitHub Actions の Node 24 移行完了**: GitHub Actions を Node 24 へ完全移行 (#996)

#### v1.4.0 の主要な変更点（2026-05-29）

- **Context unification（tool context → callbackContext）**: tool context を callbackContext にマージする内部コンテキスト統合 (#871)、 agent/context + internal/context/callback_context の統合 (#868)
- **adka2a structured error propagation**: adka2a で構造化エラーを伝搬 (#874)
- **a2a-go/v2 SDK への移行**: examples と CLI launcher を a2a-go/v2 SDK 利用へ更新 (#780)
- **metadata-only SSE チャンク許容**: StreamingResponseAggregator で metadata-only な SSE チャンクを abort せず受理し、 ストリーム中断を防止 (#918)
- **conformance test recording plugin**: 適合テスト記録用プラグインを追加 (#890)
- **a2a execution cleanup callback 修正**: cleanup callback が発火しない問題を修正 (#903)
- **unrelated function events 保持**: 無関係な function events を保持するよう修正 (#767)
- **Vertex AI function call ID 保持**: Vertex AI の function call ID を保持 (#762)
- **tool responses を confirmations より先に yield**: (#765)
- **ThoughtSignature 複製**: `adk_request_confirmation` parts に ThoughtSignature をコピー (#763)
- **replay_plugin 修正**: 空の llmresponses と function formatting を比較前に normalize (#869)
- **transfer agent validation 追加**: transfer agent に validation を追加 (#824)

#### v1.3.0 の主要な変更点（2026-05-20）

- **user auth propagation 修正 (adka2a compat)**: adka2a 互換で user auth propagation が機能していなかった問題を修正 (#861)
- **Live audio cache for save artifact**: live で save artifact 向け audio cache を追加 (#838)
- **Live streaming tools**: live で streaming tools を追加 (#836)
- **Live session resumption**: bidirectional Live ストリーミングにセッション resumption を追加 (#837)
- **Live bidirectional streaming core**: 双方向ストリーミングのコア機能を新規追加 (#833)、 sequential agent live run (#835)、 live example (#834) を同梱
- **nil deref ガード (tool.Tool 未実装)**: ツールが `tool.Tool` interface を実装していない場合の nil dereference を防止 (#855)
- **non-streaming agent の StateDelta 伝搬修正**: non-streaming agent で StateDelta を伝搬するよう修正 (#854)
- **runtime request Decode error 修正**: runtime で request の Decode エラーを無視せずハンドリング (#851)
- **Gemini モデル更新**: examples のモデルを `gemini-3.1-flash-lite` に変更 (#839)
- **Dependabot 設定追加**: genai 系依存の自動アップデート用 Dependabot 設定 (#843)
- **a2a-go nil part fix bump**: a2a-go の nil part fix を取り込むためバージョンバンプ (#827)
- **parallel HITL function test**: parallel HITL function test を追加 (#817)
- **ADK Go LLM Request タグ付け対応**: LLM Request タグ付けのため ADK Go バージョン更新 (#816)
- **adka2a public API v2 移行**: 旧 adka2a public api が新 a2a-go/v2 に依存するよう修正 (#813)
- **VertexAI MemoryBank サポート**: VertexAI MemoryBank サポート追加 (#801)
- **thought signature 伝搬修正**: mixed responses の最初の function call へ thought signature を伝搬 (#788)
- **`gen_ai.usage` 属性リネーム**: experimental reasoning tokens 属性を `gen_ai.usage.*` に rename（OTel semantic conventions 整合） (#779)
- **a2a-go/v2 対応**: ADK を a2a-go v2 に対応 (#701)
- **stream_query simple text サポート**: full `genai.Content` ではなく simple text もサポート (#773)
- **Agent Engine 既存インスタンス更新**: 既存 Agent Engine インスタンスの更新サポート (#755)
- **runner manual session ID 削除＆自動生成**: runner で手動 session ID 入力を削除し自動生成を有効化 (#754)

#### v1.2.0 の主要な変更点

- **Agent Engine 統合**: Agent Engine デプロイのフルサポート (#749)
- **Merged skill source proxy**: 複数 skill source をマージするプロキシ実装 (#747)
- **Preload frontmatters skill source proxy**: frontmatter プリロードプロキシ (#748)
- **Skill Source proxy for preloading skills**: skill preloading プロキシ (#745)
- **SkillToolset 実装**: Skill をツールセットとして提供 (#733)
- **Toolsets RequestProcessor**: Toolsets が `toolinternal.RequestProcessor` インターフェースを実装可能に (#730)
- **traceCapacity API config 修正**: API config に traceCapacity 追加 (#731)
- **adk-web SSE エラーフォーマット修正**: (#734)
- **content processor 修正**: `toolconfirmation.FunctionCallName` を除外 (#717)

#### v1.1.0 の主要な変更点

- **EventArc subrouter**: EventArc subrouter サポートと Cloud Run デプロイスクリプト統合 (#713, #716)
- **Pub/Sub trigger**: Pub/Sub トリガーセットアップと subrouter (#704, #712)
- **Skills パッケージ**: `skill.Source` インターフェースの定義とファイルシステムスキルソース実装 (#711)
- **Agent Engine デプロイ**: ADK Go CLI に Agent Engine デプロイ追加 (#715)
- **テレメトリ LRU キャッシュ**: デバッグテレメトリに設定可能な LRU キャッシュ（メモリリーク防止） (#687)
- **キャッシュ読み取り入力トークン属性**: テレメトリにキャッシュ読み取り入力トークン属性追加 (#714)

#### v1.0.0 の主要な変更点

- **正式リリース**: v1.0.0 安定版リリース

#### v0.6.0 の主要な変更点

- **Apigee モデル**: Apigee モデルサポート追加 (#639)
- **RemoteAgent パーツ変換拡張ポイント**: RemoteAgent パーツ変換の拡張ポイント (#627)
- **pathPrefix 設定**: API ランチャーに pathPrefix 設定追加 (#616)
- **Replay プラグイン**: リプレイプラグイン追加 (#618)

#### 参考リンク

- [ADK Go](https://github.com/google/adk-go)

---

### ADK JS

**現行バージョン**: **v1.3.0 (adk-v1.3.0 / devtools-v1.3.0 / main-v1.3.0、 2026-06-22)**

**チェックアウト状態**: `adk-v1.3.0-28-gca2209b` (v1.3.0 + 28 commits、 HEAD 2026-07-15。 軽量タグ運用による素の `git describe` の注意は従前どおり。 新タグ未発行)

#### 2026-07-18時点 新着 (v1.3.0 後 28 commits: Skills Registry / OpenAPI REST tool / Agent-Controlled Compaction)

- **Skills Registry**: Core interface + zip 展開 + local toolset キャッシュ fallback、 remote GCP Skills Registry 統合、 LLM Agent 向け動的 `SearchSkillsTool` (#422–#424)
- **OpenAPI REST tool**: auth helper / credential exchanger、 spec operation parser、 REST API tool を part 1–3 で実装 (#384–#386)
- **Gemini Interaction API + Compaction**: Gemini Interaction API 実装 (#364)、 Agent-Controlled Compaction (#477)、 composite session key (appName/userId/sessionId, #486)
- **Live models**: Gemini 2.5 / 3.x Live models 対応 (#409)、 `--reload_agents` ホットリロード (#304)
- **セキュリティ**: 複数の SSRF / 認証修正 (#465, #482)

#### 2026-07-01〜2026-07-05 新着 (Gemini Interaction API + OAuth2 SSRF 硬化)

- **Gemini Interaction API を adk-js に実装** (#364)
- **SECURITY: `fetchOAuth2Tokens` の OAuth2 トークンエンドポイントに SSRF ブロックリストを適用** (#465)
- **streaming: 空 part 配列の抑制修正** (#450)

#### 2026-06-30 新着 (コンテキスト圧縮とアーティファクトの session スコープ化)

- **Trajectory Thought Pruning compactor 追加**: セッション履歴の古いイベントから "thought"（思考）パートだけを剪定する `TrajectoryThoughtPruningCompactor`（`BaseContextCompactor` 実装）を新設。 因果履歴（action / observation）は保持したままトークン使用量を削減する。 末尾 `eventRetentionSize` 件は圧縮対象外。 付随して `hasThoughts` / `pruneThoughts` を Event ユーティリティへ切り出し、 `database_session_service` を対応させた (#451)
- **SessionArtifactService 導入 + ForwardingArtifactService リファクタ**: app / user / session に束縛された session スコープの artifact 操作インターフェース `SessionArtifactService` と、 既存 `BaseArtifactService` を特定 session に束ねる wrapper `ScopedArtifactService` を新設。 `ForwardingArtifactService` をこの新構造ベースに整理した (#455)

この window で新規 release タグ・SECURITY: prefix commit・破壊的変更はいずれもなし。

#### 2026-06-22 新着 (v1.3.0 リリース / integrations package / Skills Registry / --reload_agents)

**v1.3.0 (adk-v1.3.0 / devtools-v1.3.0 / main-v1.3.0) を 2026-06-22 にリリース**。 v1.2.0 後 main で進めていた以下を取り込み:

- **新規 `integrations` package** (#449): top-level の integrations package を新設
- **OpenAPI REST API tool (part 3)** (#386): v1.2.0 の parser / auth handler (part 2、 #385) に続く REST API tool を実装し OpenAPI toolchain を完成
- **Skills Registry 3部作**: Core interface + zip 展開 + local toolset cache fallback (#422)、 remote GCP Skills Registry 統合 + E2E (#423)、 LLM agent 向け動的 `SearchSkillsTool` (#424)
- **`--reload_agents` flag** (#304): agent ファイルを監視して hot-reload
- **Gemini 2.5 / 3.x Live Models サポート** (#409)
- **LlmAgent が AuthPreprocessor を使用** (#444)
- **Agent Engine デプロイ先を GCR → Artifact Registry へ** (#441): Reasoning Engine server 互換 route + headers parser を同梱 (#440)
- **concurrent replacement + key dedup** (#432)、 **ADK Web assets の動的 DL + shared folder serve** (#427)
- **SECURITY: streaming の prototype pollution 修正** (#410): model 制御 JSON path 経由の prototype pollution を防止
- **修正**: `outputSchema` + tools の無限ループ解消 (#412)、 trailing 空 STOP chunk 抑制 (#426)、 session 作成時の temp state key フィルタ (#406)、 session event key を MySQL index-safe に (#437)
- **破壊的変更**: dev server のデフォルトポートを 8000 → 8080 へ (#439)、 Agent Engine デプロイ先を GCR → Artifact Registry へ (#441、 Artifact Registry のセットアップが必要に)

#### 2026-06-18 新着 (OAuth2 SSRF 強化 / outputSchema+tools 無限ループ修正)

- **SECURITY: OAuth2 discovery の SSRF チェックで 127.0.0.0/8 と cloud-metadata ホスト名を遮断** (#431): OAuth2 discovery における SSRF guard を強化し、 loopback レンジと cloud metadata エンドポイントへのアクセスをブロック
- **outputSchema + tools 併用時の無限ループ解消** (#412): outputSchema と tools を組み合わせた際に発生する無限ループを修正（unit test も追加）

**注目**: **v1.2.0 リリース（2026-06-03）**。 v1.1.0 後に積まれていたセキュリティ / 堅牢性修正（CORS 脆弱性、 OAuth2 SSRF 防止、 HTTP 切断時 abort、 AdkApiServer host 制限等）を取り込み。 v1.2.0 後の main で進めていた **Skills Registry 3部作**（Core interface + Zip 展開 + local Toolset キャッシュ → リモート GCP Skills Registry 統合 → LLM Agent 向け動的 SearchSkillsTool、 #422-424）、 **OpenAPI spec operation parser + auth handler (part 2、 #385)**、 **streaming の prototype pollution 修正（model 制御 JSON path 経由、 セキュリティ、 #410）** は **v1.3.0（2026-06-22）でリリース**。 Python 側の Skills Registry / GCP 連携と歩調を揃えた動き。

#### 2026-06-17 新着 (Gemini 2.5/3.x Live Models / ADK Web assets 動的 DL / secure randomUUID)

- **Gemini 2.5 / 3.x Live Models サポート** (#409、 `feat(core)`): ADK JS で Gemini 2.5 / 3.x の Live モデルに対応
- **ADK Web assets の動的ダウンロード**: ADK Web の asset を動的に download し shared folder から serve (#427)
- **concurrent replacement + key dedup 有効化** (#432): key deduplication 付きの concurrent replacement をサポート
- **SSE streaming で trailing 空 STOP chunk を抑制** (#426、 `fix(streaming)`): parts ゼロの末尾 STOP chunk を抑制
- **secure randomUUID 利用** (#433、 `refactor(core)`): 利用可能なら secure な `randomUUID` を使用
- **session event key を mysql index-safe に** (#437): session event key を MySQL index に収まる形へ
- **content_processor_utils の state mutation bad practice 修正** (#430)
- **TSDoc / unit test 拡充**: LLM processors / summarizer / security plugin / a2a utils / compacted events の TSDoc + unit test (#413)、 OAuth2CredentialRefresher の unit test (#403)、 agent_transfer / tool_filter / context_compactor / content_request / agent_registry_mcp processor の TSDoc (#414)

#### v1.1.0 後の変更点（v1.2.0 に取り込み済み）

- **Agent Registry 実装**: adk-js に Agent Registry を実装 (#358)
- **CORS 脆弱性修正**: express.urlencoded parser を無効化して CORS 脆弱性を解消 (セキュリティ) (#378)
- **OAuth2 SSRF 防止**: IPv4-mapped IPv6 経由の SSRF をブロックし、 死んでいた 172.16/12 チェックを修正 (セキュリティ) (#354)
- **run_sse の hardcoded `*` 削除**: run_sse から hardcoded Access-Control-Allow-Origin ワイルドカードを削除 (セキュリティ) (#360)
- **HTTP 切断時の agent 実行 abort**: HTTP 接続が切断された際に agent 実行を abort (#382)
- **AdkApiServer host 制限**: AdkApiServer を設定された host のみで listen するよう制限 (#383)
- **OpenAPI auth helpers / credential exchangers (part 1)**: OpenAPI 向け auth helper と credential exchanger を実装 (#384)
- **customMetadata サポート**: runAsync / runEphemeral で customMetadata をサポート (#363)
- **listSessions pagination / sorting**: listSessions に pagination と sorting を追加 (#331)
- **MCP client session クローズ (Windows)**: listTools/callTool 後に MCP client session を close し、 Windows libuv assertion / プロセスリークを修正 (#333)
- **AgentTool 修正**: skipSummarization を親 EventActions に伝搬しない (#301)、 sub-agent state delta から temp: キーをフィルタ (#271)
- **function tools array response ラップ**: Gemini API 準拠のため array レスポンスをラップ (#347)
- **agent_loader esbuild external 化**: lightningcss / jiti を external に指定し、 optional deps 不在時の adk web 不具合を修正 (#319)
- **Agent Engine Sandbox Code Executor**: Agent Engine Sandbox 経由のコード実行 Executor を新規追加 (#317)
- **TSDoc `@param` 追加**: `BeforeA2ARequestCallback` と `AfterA2ARequestCallback` に `@param` TSDoc 追加 (#339)
- **injectSessionState ユニットテスト**: instructions の `injectSessionState` に unit test 追加 (#338)
- **runWithRouting failover_utils テスト**: `runWithRouting` の unit test 追加 (#336)
- **file_extension_utils テスト**: file_extension_utils の unit test 追加 (#337)
- **Vertex AI Memory Bank service**: Vertex AI Memory Bank service を新規実装＋テスト (#291)
- **Agent Engine Sessions サポート**: Agent Engine Sessions サポート追加 (#249)
- **Google Maps tool**: 新規 Google Maps ツール追加 (#321)
- **VertexRagRetrievalTool**: Vertex AI RAG Engine を使ったグラウンディング向け retrieval ツール (#277)
- **stringifyContent / AgentTool thought parts フィルタ**: thought parts を出力からフィルタ (#323)
- **Windows 互換性**: dev/build.js で unix `cp` を Node.js fs.cp に置換 (#318)
- **MCPToolset.getTools() toolFilter 適用**: getTools() でも toolFilter を適用するよう修正 (#312, #313)
- **StreamingResponseAggregator.close() drop 修正**: 最後のチャンクに candidates が無い場合の drop を修正 (#289, #311)

#### v1.1.0 の主要な変更点

- **UrlContextTool**: Gemini 2+ の URL context グラウンディング向け UrlContextTool 追加 (#303)
- **Vertex AI Search Tool**: Vertex AI Search ツール追加 (#296)
- **MCP プレフィックス strip**: ツール実行時にプレフィックスを strip 修正 (#299)
- **AgentTool セッション再利用**: 同一セッション内での再利用のため `getOrCreateSession` 使用 (#302)
- **adk web UI ソース提供パス修正**: (#309)
- **js-yaml 利用**: yaml パッケージから js-yaml に変更 (#293)

#### v1.0.0 の主要な変更点

**[Core / Features]**

- **正式リリース**: v1.0.0 への昇格 (#229)
- **Progressive model streaming processing**: プログレッシブモデルストリーミング処理 (#258)
- **Skills システム**: script execution (#276)、loader part 3 (#256)、toolset part 2 (#252)、skills interface (#251)
- **Abort parameter サポート**: runner / agent / model / tool / processors で abort パラメータ対応 (#234)
- **RoutedAgent / RoutedLlm**: ルーティング可能なエージェント・LLM（experimental） (#215)
- **Unsafe local code executor**: unsafe ローカルコードエグゼキューター (#257)
- **Plugin callbacks for context compaction and tool selection**: プラグインコールバック (#250)
- **Auth preprocessor**: 認証プリプロセッサー (#227)
- **OAuth2 サポート**: OAuth2 関連クラス (#225)
- **AdkApiServer エクスポート**: `@google/adk-devtools` から export (#245)
- **Agent type alias for LlmAgent**: Python ADK とのパリティ (#242)

**[Bug Fixes]**

- **custom URL options for DB 接続**: client URL 対応 (#284)
- **thoughtSignature 伝播修正**: 並行 function calls streaming 時の伝播 (#268)
- **ESM dynamic require 対応**: esm ビルドでの `__dirname`/`__filename`/`import.meta.url` 保持 (#254)
- **ESM dynamic require 修正**: (#244)
- **invocation id 追加**: parallel tool responses マージ時の invocation id 追加 (#253)
- **otel 依存関係移動**: dev deps → deps に移動 (#243)

**[Security / Deps]**

- **パストラバーサル防止**: FileArtifactService (CWE-22)
- **lodash / lodash-es セキュリティ更新**: (#232, #230)
- **follow-redirects bump**: (#275)
- **vite bump**: npm_and_yarn group (#236)

#### v0.2.4 の主要な変更点

- **A2A 統合**: CLI オプションによる A2A 経由のエージェント提供 (#188)
- **トークンベースコンテキストコンパクション**: (#191)
- **セッション DB 初期化修正**: (#195)
- **MikroORM リファクタリング**: セッションサービスのリファクタ

#### 参考リンク

- [ADK JS](https://github.com/google/adk-js)

---

### Agent Starter Pack

**現行バージョン**: v0.41.3

**チェックアウト状態**: `v0.41.3-1-g659f047` (v0.41.3 + 1 commit、 HEAD 2026-05-21)

**注目**: README で後継プロジェクト「agents-cli」への進化告知 (#952)、 直近では **maintenance mode に入ったことを公式に surface し、 ユーザーを agents-cli に push** (#967)。 Google の agent dev tooling 戦略は事実上 agents-cli へ移行。

#### v0.41.3 後の変更点

- **maintenance mode 公式アナウンス**: README / ドキュメントで maintenance mode 入りを surface し、 agents-cli への移行を push (#967)

#### v0.41.3 の主要な変更点

- **バージョンバンプ**: v0.41.3 へのバージョンバンプ (#953)

#### v0.41.2 の主要な変更点

- **uv lock 再生成 + langgraph-prebuilt pin**: `langgraph-prebuilt<1.0.9` への pin (#948)
- **agents-cli 発表**: Agent Starter Pack の次世代進化として agents-cli 告知 (#952)

#### v0.41.1 の主要な変更点

- **バージョンバンプ**: v0.41.1 へのバージョンバンプ (#944)

#### v0.41.0 の主要な変更点

- **デフォルトリージョン変更**: デフォルトリージョンを us-east1 に変更

#### v0.40.1 の主要な変更点

- **Vertex AI モデル名修正**: 接続チェック時の有効なモデル名使用 (#919)
- **BQ アナリティクステーブル名更新**: `agent_events` テーブル名に更新 (#924)

#### v0.40.0 の主要な変更点

- **adk-py@ ショートカット**: google/adk-python contributing samples 用ショートカット追加 (#918)
- **Gemini Enterprise アプリフィルタ**: `list_gemini_enterprise_apps` に `appType` フィルタ追加 (#912)

#### 参考リンク

- [Agent Starter Pack](https://github.com/GoogleCloudPlatform/agent-starter-pack)

---

### Cloud Run MCP

**現行バージョン**: v1.10.0

**チェックアウト状態**: `v1.9.0-60-g63bd8cc` (`git describe` は祖先タグ `v1.9.0` + 60 だが package.json は `1.10.0`。 `v1.10.0` タグは別コミット `6ce7cbb` の別系列で HEAD の祖先ではない、 HEAD 2026-07-09。 下記 Docker Compose 機能群は未だ tag 付き release 未反映の未リリース分)

#### 2026-07-18時点 新着 (Docker Compose → Cloud Run 直接デプロイ機能群 = 未リリース)

- **Docker Compose デプロイ対応**: `deployCompose` capability を新設し、 Cloud Run へ compose 定義から直接デプロイ可能に (#252, #272)
- **run-compose 連携**: compose 変換用 `run-compose` バイナリの download/実行、 並列ビルドと translate (#244, #245, #253, #249)
- **Compose リソース拡張**: volume mounts (#254)、 Secret Manager (#256)、 AI models (#258) を compose デプロイでサポート
- **Cloud Build 統合** (`cloudbuild.yaml` + BUILD_ID 定期ビルド, #269, #275)、 **Cloud Run skills 同梱** (#267)
- 破壊的変更: なし

#### 2026-06-29 新着 (archiver v8 移行)

- **archiver 8.0.0 へ upgrade**: 内部の zip/tar 生成ユーティリティ (`lib/util/archive.js`) が archiver v7→v8 の破壊的 API 変更に追随。 従来の factory 関数 `archiver('zip'|'tar', …)` が廃止され、 名前付き class export `new ZipArchive({ zlib })` / `new TarArchive({ gzip })` を使う形へ書き換え。 あわせて `test/local/archive.test.js` を新規追加。 ユーザ向け挙動 (デプロイ時のソースアーカイブ) は不変で、 依存ライブラリの upstream 破壊的変更を内部で吸収したもの (#297)

#### v1.10.0 後の変更点

- **hono 4.12.x 継続バンプ**: 直近 HEAD まで hono 等の依存パッチバンプが継続 (〜#294)
- **@protobufjs/utf8 1.1.0 → 1.1.1 バンプ**: 依存パッチバンプ (#282)
- **fast-uri 3.1.2 / fast-xml-builder 1.2.0 / hono 4.12.18 バンプ**: 依存パッチバンプ群 (#281, #280, #279)
- **ip-address / express-rate-limit バンプ**: セキュリティパッチ群 (#277)
- **Docker Compose デプロイメントサポート**: docker compose deployments を Cloud Run へ展開可能に (#272)
- **BUILD_ID ベース cloudbuild**: scheduled builds 向け BUILD_ID base の cloudbuild 追加 (#275)
- **cloudbuild image location 修正**: イメージ配置のロケーション修正 (#273)
- **README SKILL.md リンク修正**: (#276)
- **Cloudbuild 設定**: `cloudbuild.yaml` 追加 (#269)
- **Cloud Run skills**: cloud run skills 追加 (#267)
- **named/bind ボリューム権限修正**: (#262)
- **AI モデルサポート**: run compose で AI モデルサポート (#258)
- **Secrets Manager サポート**: compose デプロイメントで Secrets Manager サポート (#256)
- **ボリュームマウントサポート**: (#254)
- **並列ビルド**: run compose での並列ビルドサポート (#253)
- **deployCompose capability**: (#252)
- **translate functionality for run compose**: (#249)
- **サービス情報詳細化**: getInfo でより詳しい情報提供 (#248)
- **SECURITY.md 追加**: (#247)
- **run-compose binary 統合**: binary ダウンロードとリソースコマンド実行 (#244, #245)
- **artifact download ロジックリファクタ**: 再利用可能化 (#240)
- **依存関係更新**: Hono 4.12.14、fast-xml-parser 5.7.1、lodash 4.18.1、path-to-regexp 8.4.0、picomatch 4.0.4 等

#### v1.10.0 の主要な変更点

- **cloud-run-mcp クライアント**: OSS Run MCP からのデプロイ用クライアント追加 (#242)
- **Ingress ポリシー環境変数**: 環境変数によるイングレスポリシー設定 (#243)
- **Run v1 クライアント**: googleapis ベースの Run v1 クライアント追加 (#236)
- **統合テスト拡充**: Java, Node.js, Python プロジェクトの統合テスト追加

#### 参考リンク

- [Cloud Run MCP](https://github.com/GoogleCloudPlatform/cloud-run-mcp)

---

### gcloud-mcp

**現行バージョン**: gcloud-mcp-v0.5.3 / storage-mcp-v0.6.0 / observability-mcp-v0.2.3 / backupdr-mcp-v0.1.0

**チェックアウト状態**: `release-please-422-19-g238728f` (storage-mcp-v0.6.0 release-please ブランチから 19 commits 先、 HEAD 2026-07-15。 `release-please-NNN` は semver でなく bot tag)

#### 2026-07-18時点 新着 (storage-mcp 0.6.0 の破壊的変更 + 依存 bump)

- **破壊的**: **storage-mcp 0.6.0 で `download_object_safe` tool を削除 (#420)** — 当該 tool 利用の client は代替へ移行が必要。 0.5.1 で `delete_object` を safe→destructive へ移動 (#412)
- **gcloud-mcp 0.5.3**: Windows 互換リファクタ (#342)、 integration test 修復 (#426)
- pin 先頭 19 commit はほぼ依存 bump (js-yaml / hono / @grpc/grpc-js / googleapis v172 等)

#### storage-mcp-v0.6.0 後の変更点

- **依存標準更新**: standard dependency updates (#428)
- **turbo v2.9.14 バンプ (security)**: turbo を v2.9.14 にセキュリティ更新 (#430)
- **@tootallnate/once 2.0.0 → 2.0.1 バンプ**: 依存パッチバンプ (#431)
- **qs 6.15.0 → 6.15.2 バンプ**: 依存パッチバンプ (#432)
- **protobufjs 7.5.6 → 7.6.1 バンプ**: 依存マイナーバンプ (#436)
- **googleapis v172 更新**: googleapis 依存を v172 に更新 (#433)
- **brace-expansion 5.0.5 → 5.0.6 バンプ**: 依存パッチバンプ (#429)
- **fast-uri 3.1.0 → 3.1.2 バンプ**: dev deps バンプ (#427)
- **依存標準更新**: standard dependency updates (#399)

#### storage-mcp-v0.6.0 の主要な変更点（2026-05-06）

- **`download_object_safe` ツール削除（破壊的変更）**: 「safe」を名乗っていたが実際は destination パスへの ~/.bashrc 等への書き込みを許す設計だったため削除。 destructive 経路の `download_object` または `read_object_content` / `read_object_metadata` への移行が必要 (#420, #422)
- **integration tests 修復**: MCP 接続不能による失敗を修正 (#421, #426)
- **依存バンプ群**: hono 4.12.12 → 4.12.18 (#425)、 ip-address / express-rate-limit (#423)、 protobufjs 7.5.4 → 7.5.6 (#417)、 postcss 8.5.6 → 8.5.12 (#416)、 fast-xml-parser 5.5.7 → 5.7.1 (#415)、 codecov-action v6 (#410)

#### storage-mcp-v0.5.1 の主要な変更点

- **`delete_object` を destructive に移動**: safe tools から destructive tools へ移動（セキュリティ強化） (#412)
- **gemini mcp list `--debug` フラグ**: 出力切り詰め解消のための debug フラグ追加 (#405)

#### storage-mcp-v0.5.0 の主要な変更点

- **安全なオブジェクトダウンロードツール**: 安全なダウンロードオブジェクトツール追加、オリジナルを destructive とマーク (#403)
- **カスタム User-Agent**: Storage クライアントにカスタム User-Agent 設定 (#407)
- **`list_buckets` 修正**: `userProject` の代わりに `project` を使用するよう修正 (#408)

#### 主要な変更点

- **backupdr-mcp v0.1.0**: Backup DR MCP サーバー新規追加 (#372, #380)
- **storage-mcp v0.3.3**: ストレージコンポーネント更新 (#358)
- **observability-mcp v0.2.3**: オブザーバビリティコンポーネント更新 (#357)
- **Windows 互換性**: リファクタリング (#342)

#### 参考リンク

- [gcloud-mcp](https://github.com/googleapis/gcloud-mcp)

---

### Gemini Cloud Assist MCP

**現行バージョン**: v0.8.0 (2026-04-21)

**チェックアウト状態**: `v0.8.0-6-ga0439a7` (v0.8.0 + 6 commits、 HEAD 2026-05-19)

**注目**: ローカル Node.js 実装 (v0.2.0) を **完全 deprecate**、 Remote MCP Server 構成へアーキテクチャ全面刷新。 現在 **Private Preview** で allowlist 制（Google Cloud account team 経由でアクセス申請が必要）。

#### v0.8.0 後の変更点（次回リリース向け）

- **skills 更新**: bundled skills の更新 (a0439a7)
- **Claude Code Instructions 追加**: Claude Code 向け instructions を README/プロジェクトドキュメントに追加 (540474b, 22a2a18)
- **README MCP Tool description 更新**: MCP Tool 説明と Claude Code 向け instructions を README に取り込み (997bb4d, 8580afd)
- **GitHub workflows cleanup / 修正**: CI ワークフローの整理 (a8c60dc)

#### v0.8.0 の主要な変更点

- **Remote MCP Server 化**: ローカル Node.js MCP server から **Remote MCP Server architecture** へ全面移行（**破壊的変更**） (d225f7b)
- **ローカル Node.js server の完全 deprecate**: v0.2.0 の local server 完全廃止 (d5d860b)
- **Private Preview ローンチ**: Gemini Cloud Assist remote MCP Server を Private Preview として正式公開
- **Skills 群追加**: `designing-and-deploying-infrastructure`、 `operating-google-cloud` の 2 種類の Skill 定義追加
- **README に deprecation notice / Private Preview notice 追加**: ローカル版 deprecation とリモート版アクセス申請手順を明示

#### v0.2.0 / v0.1.x（legacy local Node.js）の主要な変更点

- **npm パッケージ公開**: `@google-cloud/gemini-cloud-assist-mcp` を npm 公開 (e24e526)
- **mcpName / インストール手順整備**: `mcpName` フィールド追加と Claude Desktop / npm パッケージ経由のインストール手順整備 (831c72e, 4a7afda)
- **version sync スクリプト**: ツーリングへ追加 (94cc346)
- **npm publish workflow**: GitHub Actions で npm publish 自動化 (6b00fa5)

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| Local Node.js server → Remote MCP Server (v0.8.0) | クライアント設定をリモートエンドポイント参照に変更必須、ローカル install 系手順は無効化 |

#### 参考リンク

- [Gemini Cloud Assist MCP](https://github.com/GoogleCloudPlatform/gemini-cloud-assist-mcp)
- [Use the Gemini Cloud Assist remote MCP server (Cloud Docs)](https://docs.cloud.google.com/cloud-assist/use-gemini-cloud-assist-mcp)

---

### GKE MCP

**現行バージョン**: **v0.14.0 (2026-07-06)**

**チェックアウト状態**: `v0.14.0-10-g329c8b4` (v0.14.0 + 10 commits、 HEAD 2026-07-14。 release version は据え置き、 下記は未リリース分)

#### 2026-07-18時点 新着 (v0.14.0 後・未リリース)

- **`query_traces` MCP tool**: Google Cloud Trace 用 tool を追加 (#467) — 直近の目玉
- **eval スイート整備**: JobSet interruption (#458)、 GPU/TPU disruption (#460)、 TPU vbar OOM (#457) の multi-case 評価
- 依存更新中心 (anthropic-sdk-go / google.golang.org/genai・api / adk)。 破壊的変更なし

#### v0.14.0 リリース (2026-07-06) の主要な変更点

- **`verify_unused` クラスタ安全性チェック skill 追加** (#444)
- **GKE TPU dynamic slices の監視・管理 skill 追加** (#442)
- **query_logs に View パラメータ (BASIC|FULL) を追加**: コンパクトなログエントリ出力に対応 (#449)
- **依存更新**: google.golang.org/adk 1.4.0 → 1.5.0 (#455)、 **adk-anthropic-go 0.1.18 → 1.0.0（メジャー、 #454）**、 anthropic-sdk-go 1.56.0 (#453)、 google.golang.org/api 0.287.0 (#452)、 ui npm グループ 9 件 (#456)
- version を 0.14.0 に更新 (#451)。 明示的な破壊的変更マーカーなし（v0.13.0 以降の新着として記録済みの skill 群を正式タグ化）

#### 2026-07-01 新着 (TPU メトリクス監視スキル追加)

- **gke-tpu-metrics-monitoring スキル追加**: GKE system metrics と PromQL を使い TPU ワークロード/ノード/ノードプールを監視・トラブルシュートする skill。 ワークロードの中断や性能劣化が基盤インフラ起因かを診断する。 `SKILL.md` に加え `EVAL.yaml` / `TEST.md` / `references/failure_signatures.md` / `scripts/validate_queries.sh` を同梱 (#443)

#### 2026-06-29 新着 (GPU/TPU 障害対応スキル + UI 脆弱性修正)

- **GPU/TPU ホストメンテナンス障害対応スキル追加**: skill `gke-ai-troubleshooting-handle-disruption-gpu-tpu`。 Compute Engine のホストメンテナンス時に GPU/TPU ワークロードで起きるノード disruption を診断・予測する。 予定メンテナンスのチェックを起点にした診断ワークフロー付き (#430)
- **UI 依存の脆弱性修正 (セキュリティ)**: `ui/package-lock.json` を更新し UI 依存の脆弱性を解消。 主に Babel toolchain 系の transitive 依存 (@babel/core 等 7.29.x へ) の bump (#448)

#### 依存 bump のみ (2026-06-29、実質変更なし)

- `github.com/anthropics/anthropic-sdk-go` 1.50.1 → 1.51.1 → 1.53.0 (#434, #446)
- `google.golang.org/genai` 1.61.0 → 1.62.0 (#445)
- all-npm group 10 件まとめ bump (#447)
- (dev) `@types/node` 25.9.3 → 26.0.0 in /ui (#437)
- (ci) `actions/checkout` 6 → 7 (#432)

#### 2026-06-26 新着 (Developer Knowledge API docs / manifestgen mapping / DK 404 修正)

- **Developer Knowledge API の環境変数 / セットアップ doc 追加** (#439)
- **manifestgen: `giq_fetch_model_server_versions` を gcloud command にマッピング** (#428)、 **`giq_fetch_model_servers` を gcloud command にマッピング** (#427)
- **DK `SearchDocuments` の HTTP method を GET に修正し 404 を解消** (#440)
- **manifestgen instruction 重複修正 + Developer Knowledge 利用必須化** (#438)
- **`instruction.md` を登録済み MCP schema に整合** (#405)
- **依存バンプ**: hono 4.12.23 → 4.12.27 (#441)、 google.golang.org/api 0.284.0 → 0.286.0 (#433)、 genai 1.60.0 → 1.61.0 (#435)、 super-linter 8.6.0 → 8.7.0 (#431)

#### 2026-06-18 新着 (gke-skill-creator meta-skill)

- **gke-skill-creator meta-skill 追加** (#419): GKE 向け skill を生成する meta-skill（skill を作るための skill）を新設

**注目**: **v0.13.0 が 2026-05-28 にリリース**。 v0.12.0 の Anthropic Claude ADK adapter / node pool 管理ツールに続き、 k8s リソース操作ツール群（apply / get / describe / patch / delete / logs / rollout status / auth check / api resources / cluster info / events）を一括拡充。 install 時の checksum verification とセキュアな CI（insecure `pull_request_target` 防止チェック）も追加。 v0.13.0 以降は依存バンプが続行中（google.golang.org/api、 genai、 anthropic-sdk-go、 kubernetes group、 esbuild、 npm group 等）。

#### 2026-06-15 新着 (依存バンプのみ)

NO_NEW_COMMITS — HEAD 日付のみ 2026-06-15 に更新。 google.golang.org/api 0.283.0 → 0.284.0 (#423)。

#### 2026-06-13 新着 (Anthropic SDK / Kubernetes / esbuild バンプ)

- **anthropic-sdk-go 1.48.0 → 1.50.1**: Anthropic SDK Go をバンプ (#424)
- **kubernetes group 3 件 update**: k8s 依存を更新 (#422)
- **esbuild 0.28.0 → 0.28.1**: UI の esbuild を更新 (#421)
- **google.golang.org/genai 1.59.0 → 1.60.0**: genai SDK をバンプ (#425)
- **NPM group 9 件 update (UI)**: npm 依存を更新 (#426)

#### 2026-06-10 新着 (skill evals を yaml へ)

- **skill evals を textproto → yaml へ移行**: OSS との整合のため skill evals を textproto から yaml フォーマットへ移行 (#420)

#### v0.13.0 の主要な変更点（2026-05-28）

- **k8s リソース操作ツール群拡充**: `list_k8s_api_resources` (#378)、 `patch_k8s_resource` (#387)、 `get_k8s_rollout_status` (#386)、 `check_k8s_auth` (#385)、 `describe_k8s_resource` (#388)、 `get_k8s_cluster_info` (#379)、 `get_k8s_logs` (#370)、 `delete_k8s_resource` (#368) を新規実装
- **delete デフォルト cascade policy を background 化**: k8s delete のデフォルト cascade policy を background に設定 (#376)
- **install checksum verification**: インストール時の checksum 検証を追加 (#398)
- **insecure `pull_request_target` 防止チェック (CI)**: 安全でない `pull_request_target` 利用を防ぐ CI チェックを追加 (#400)
- **eval-on-pr workflow 削除**: eval-on-pr ワークフローを無効化のうえ完全削除 (#397, #399)
- **依存バンプ群**: google.golang.org/adk 1.2.0 → 1.3.0 (#393)、 genai 1.57.0 → 1.58.0 (#392)、 anthropic-sdk-go 1.43.0 → 1.45.0 (#394)、 adk-anthropic-go 0.1.15 → 0.1.16 (#395)、 go-sdk 1.6.0 → 1.6.1 (#391)、 api 0.279.0 → 0.280.0 (#390)、 all-npm group 7 件 (#396)、 qs 6.15.0 → 6.15.2 (#382)
- **manifestgen developer knowledge instructions**: manifestgen に developer knowledge の利用指示を追加 (#371)
- **`apply_k8s_manifest` ツール実装**: k8s manifest を適用する MCP ツールを新規実装 (#358)
- **ADK Anthropic Claude Go ライブラリ統合**: `Alcova-AI/adk-anthropic-go` を統合 (#356)
- **dk: SearchDocuments / GetDocuments / AnswerQuery 実 HTTP 接続化**: Developer Knowledge 3 ツールを mock から実 HTTP 接続へ昇格 (#344, #345, #346)
- **Baseline Evaluation Label Requirement 削除**: Baseline Evaluation の必須ラベル要件を撤廃 (#369)
- **anthropic-sdk-go 1.42.0 → 1.43.0 バンプ** (#364)
- **google.golang.org/genai 1.56.0 → 1.57.0 バンプ** (#363)
- **all-npm group 7 件アップデート (UI)** (#365)
- **`get_k8s_version` ツール**: K8s バージョン取得ツール追加 (#353)
- **Cluster operations support**: cluster operations サポートと unit test 改善 (#328)
- **DK 実 HTTP 接続実装**: `SearchDocuments` を実 HTTP 接続化、 mock 実装から本物のAPI接続へ昇格 (#344)
- **OWNERS / automatic reviewers 更新**: owners と自動レビュアー設定を更新 (#355)
- **eval skips 削除**: evaluation skip ロジックを削除 (#354)
- **`list_k8s_events` ツール実装**: k8s イベント一覧ツールを新規実装 (#329)
- **baseline evals feature branches トリガー化**: baseline evaluation を feature branch でも実行 (#352)
- **eval-on-pr `pull_request_target` 化**: eval CI を pull_request_target で実行 (#347)
- **`dk_get_documents` ツール定義**: Developer Knowledge get-documents ツール定義 (#324)
- **`get_k8s_resource` MCP ツール**: client-go を使った k8s リソース取得 MCP ツール (#327)
- **`dk_search_documents` ツール定義**: Developer Knowledge search-documents ツール定義 (#326)
- **`dk_answer_query` ツール定義**: Developer Knowledge answer-query ツール定義 (#325)
- **DeepEval CI/CD 統合**: PR 向け DeepEval テストと CI/CD ワークフロー実装 (#323)
- **Developer Knowledge API クライアント統合**: developer knowledge api client を統合 (#319)
- **`giq_fetch_model_servers` instructions**: manifestgen に giq_fetch_model_servers の利用指示追加 (#307, #308)
- **UI 依存バンプ**: hono 4.12.14 → 4.12.18 (#322)、 ip-address / express-rate-limit (#320), fast-uri 3.1.0 → 3.1.2 (#331)
- **Go / NPM 依存バンプ群**: anthropic-sdk-go 1.39.0 → 1.42.0 (#342), genai 1.55.0 → 1.56.0 (#339), gkerecommender 0.5.0 → 1.0.0 (#340), google-cloud group (#337)
- **CI アクションバンプ**: google-github-actions/auth v2 → v3 (#336), actions/checkout v4 → v6 (#335), setup-go v5 → v6 (#334), setup-python v5 → v6 (#333)

#### v0.12.0 の主要な変更点

- **ADK Anthropic Claude アダプター実装**: LLM 抽象 factory + Anthropic Claude 用 ADK adapter (#280, #303)
- **Node Pool 管理ツール追加**: GKE node pool の create/list/update 等の管理ツール (#282)
- **新規 cluster ツール群＋GKE remote MCP 機能**: 新規クラスタ操作ツールと GKE remote MCP 連携 (#281)
- **giq fetch_model_servers / fetch_profiles**: model servers と profiles の fetch ツールを実装し manifest agent と接続 (#284, #285, #290, #293, #279)
- **manifestgen rename**: `giqTool` → `generateManifestTool` (#306)
- **GKE AI TPU 接続障害トラブルシュート skill**: (#267)
- **GKE AI トラブルシュート skill 作成ガイド**: (#268)
- **dependency バンプ群**: google-cloud groups (#296), modelcontextprotocol/go-sdk 1.5→1.6 (#298), google.golang.org/api (#297), genai 1.54→1.55 (#299)
- **auto-request-review 追加**: (#305)

#### v0.11.1 後の変更点

- **GIQ ツール manifest agent 統合**: `giq_generate_manifest` をマニフェストエージェントに統合 (#253)
- **GIQ コアロジックを MCP transport から分離**: (#251)
- **ADK フレームワーク統合 (manifest agent)**: manifest agent に ADK 統合 (#247)
- **Skills インストール手順**: README に Skills インストール手順追加 (#252)
- **backend vertex pool 抽象化**: エージェントモック分離 (#240)
- **gke-productionize skill ガイドライン強化**: (#242)
- **gke-workload-security skill pathing 修正**: (#248)

#### v0.11.1 の主要な変更点

- **go-version-file 使用**: release プロセスで go-version-file を使用、v0.11.1 へバージョンバンプ (#238)
- **manifestgen リッチインストラクション埋め込み**: (#218)
- **Hono 依存関係更新**: UI の Hono 4.12.12 → 4.12.14 (#237)

#### v0.11.0 の主要な変更点

- **MUI 依存関係最新化**: Material-UI 依存関係を最新バージョンに更新 (#233)
- **NPM 依存関係更新**: globals, typescript 等の更新 (#234)
- **CI markdownlint/Prettier 競合修正**: markdownlint ルールと Prettier フォーマットの CI 競合修正 (#232)
- **Dependabot NPM 設定**: NPM 用 dependabot 設定追加 (#220)
- **CI アクション更新**: actions/checkout v6, actions/setup-node v6, actions/setup-go v6 (#223-#225)

#### v0.10.0 の主要な変更点

- **Golden Image Finder スキル**: ゴールデンイメージ検索スキル追加
- **Docker イメージサポート**: Docker イメージのサポート追加 (#183)
- **GKE Workload Scaling スキル**: ワークロードスケーリングスキル追加
- **ComputeClasses スキル**: ComputeClasses 作成スキル追加
- **Shell Command Injection 修正**: `ui/scripts/build.ts` のシェルコマンドインジェクション脆弱性修正（セキュリティ）

#### 参考リンク

- [GKE MCP](https://github.com/googleapis/gke-mcp)

---

### Google Analytics MCP

**現行バージョン**: **0.6.0 (2026-05-21)**

**チェックアウト状態**: `0.6.0-7-gc09abcb` (0.6.0 + 7 commits、 HEAD 2026-06-29)

#### 2026-06-29 新着 (依存パッチ更新)

- **google-analytics-admin を 0.30.1 へ**: `pyproject.toml` の pinned 依存 `google-analytics-admin==0.30.0` → `0.30.1` へパッチ bump (Renovate 自動 PR)。 破壊的変更なし (#188)

#### 2026-06-25 新着 (CI/build chore のみ)

- **CI: actions/checkout を v7 に pin** (#181、 Renovate)
- **build: zizmor findings 修正** (#183): GitHub Actions 静的解析 zizmor の指摘を解消

#### 2026-06-11 新着 (Claude Code 向け導入手順)

- **Claude Code 向けセクション追加**: README に Claude Code 用の Google Analytics MCP セットアップセクションを追加 (#174)

#### 0.6.0 の主要な変更点（2026-05-21）

- **subprocess stdio handle inheritance 防止**: サブプロセスでの stdio handle 継承を抑止し、 v0.4.0 #151 修正のフォローアップ deadlock を解決 (#154)

#### 0.5.0 の主要な変更点

- **conversions schema/spec ツール追加**: 新しい conversions schema / spec 用ツール追加 (#161)
- **google-analytics-data v0.22.0**: 依存バンプ (#159)
- **google-analytics-admin v0.29.0**: 依存バンプ (#158)

#### v0.4.0 の主要な変更点

- **tool call deadlock / stdout corruption 修正**: tool call の deadlock と stdout プロトコル汚染を解決 (#151)

#### v0.3.0 の主要な変更点

- **`run_funnel_report` ツール追加**: GA Data API v1alpha を使った funnel レポートツール (#127)
- **ADK 開発向け Skills 追加**: ADK 開発の Skills 群を Google Analytics MCP に同梱 (#148)

#### v0.2.0 以降の変更点

- **google-adk 最低バージョン更新 (セキュリティ)**: google-adk 最低バージョンを 1.28.1 に更新、脆弱性 GHSA-rg7c-g689-fr3x 対応 (#137)
- **MCP スキーマ互換性改善**: MCP スキーマ互換性と LLM ガイダンスの改善
- **ADK 移行**: Google ADK を使用するよう移行
- **google-analytics-admin 更新**: v0.28.0 へ更新
- **google-analytics-data 更新**: v0.21.0 へ更新

#### v0.2.0 の主要な変更点

- **ADK スキーマ型修正**: null 型の除去修正
- **pipx 対応**: サーバーの pipx 利用対応

#### 未リリースの破壊的変更

| 変更 | 影響 |
|------|------|
| パッケージ名を `analytics-mcp` にリネーム (#44) | インストールコマンドの変更が必要 |

#### 参考リンク

- [Google Analytics MCP](https://github.com/googleanalytics/google-analytics-mcp)

---

### MCP (Google Cloud)

**現行バージョン**: 継続的デプロイ（バージョンタグなし）

**性質**: Google 公式の MCP サーバーディレクトリ・デプロイガイダンス・入門例を集約するリポジトリ（継続デプロイ）。

#### 2026-06-18 新着 (Angular CLI MCP 追加)

- **Angular CLI MCP の追加** (#38): Angular CLI MCP サーバーをディレクトリ / 例に組み込み

#### 最近の変更点

- **bakery demographics.csv 修正**: launchmybakery デモの demographics.csv から `median_household_income` 列を除去し、 dataset description を修正 (#53)
- **リモート MCP サーバー・例セクション更新**: (#44)
- **bakery デモ自動化**: `--quiet` フラグで gcloud mcp 有効化をオートメーション化
- **launchmybakery cold start 修正**: MCP エンドポイントに明示的タイムアウト設定（cold start 対応）
- **bakery ADK version pin**: ADK tool を v1.28.0 に pin、Ctrl+C 停止手順追加
- **bakery bigquery.googleapis.com 有効化**: `setup_env.sh` で API 有効化
- **Cloud Data MCP サンプル**: DK と Cloud SQL remote MCP のラボ追加 (#22)
- **デモ動画・バッジ**: README にデモ動画・バッジ追加
- **Chrome DevTools サーバー**: 新規 MCP サーバー追加

#### 主要な変更点

- **Gemini 3.1 Pro Preview**: ルートエージェントモデルを gemini-3.1-pro-preview に更新
- **リモートサーバー集約**: AlloyDB, BigQuery, Bigtable, Cloud Resource Manager, Cloud SQL (MySQL/PostgreSQL/SQL Server), Compute Engine, Firestore, Google Maps, Chronicle, GKE, Spanner, Cloud Run, Cloud Storage
- **オープンソース MCP サーバー統合**: Workspace, Firebase, Cloud Run, Google Analytics, MCP Toolbox, GCS 等

#### 参考リンク

- [Google Cloud MCP](https://github.com/google/mcp)

---

### MCP Security

**現行バージョン**: secops-v0.7.0 (2026-03-14)

#### v0.7.0 以降の変更点

- **`list_parsers` ツール追加**: secops-mcp に `list_parsers` ツールを追加し、parser management の return type を標準化、pagination token 対応 (#252)
- **pyink フォーマット適用**: parser_management.py に pyink フォーマット適用
- **SOC ペルソナドキュメント**: SOC ペルソナをドキュメントに追加 (#245)
- **gemini-extension.json 移動**: トップレベルへのリファクタ

#### v0.7.0 の主要な変更点

- **Rule Exclusions 管理ツール**: ルール除外管理ツール追加 (#242)

#### v0.6.0 の主要な変更点

- **Investigation 管理ツール**: 調査管理ツール追加 (#220)
- **Watchlist 管理ツール**: ウォッチリスト管理ツール追加 (#222)
- **Remote MCP サーバー**: リモート MCP サーバー実装とドキュメント (#215)

#### 参考リンク

- [MCP Security](https://github.com/google/mcp-security)

---

### GenAI Toolbox

**現行バージョン**: **v1.7.0 (2026-07)**

**チェックアウト状態**: `v1.7.0-1-g3fb5a3f2cdf` (v1.7.0 + 1 commit = #3627 Dataplex テスト cleanup、 HEAD 2026-07-17。 リポ URL は `googleapis/mcp-toolbox` に改称)

#### 2026-07-18時点 新着 (v1.6.0 → v1.7.0: ArcadeDB / Dataplex data-product / ClickHouse vector)

- **ArcadeDB 対応**: arcadedb source と tools を新規追加 (#2961)
- **quotaProject 対応**: BigQuery / Looker conversational analytics で quotaProject を指定可能に (#2610)
- **Dataplex 拡充**: create/update data product・create/update data asset・get data asset tools を追加 (#3574, #3503, #3504)
- **ClickHouse ベクトル**: `clickhouse-sql` tool に native vector embedding サポートを追加 (#3229)
- **Postgres connectTimeout** (#3620)、 parameters が非 string 型で panic せずエラーを返す修正 (#3516, #3512)
- 破壊的変更: なし (v1.7.0 に BREAKING CHANGES 記載なし)

**注目**: **v1.6.0 リリース（#3495）**。 目玉は **MCP 2026 draft spec のサポート追加** (#3544) — `vdraft` プロトコル実装を新設し `--enable-draft-specs` フラグで opt-in、 draft spec の正式リリースは暫定 2026-07-28 予定 (既存 v20241105 / v20250326 / v20250618 / v20251125 と並列運用)。 サプライチェーン面では **Kokoro code signing を release workflow に統合し Toolbox バイナリへ電子署名** (#3528、 unsigned/signed GCS bucket 分離 + 署名検証ユーザガイド追加、 長年の issue #996 対応)。 tool 面は **Dataplex data-product 系 tool 拡充** (`dataplex-get-data-product` #3499 / `dataplex-list-data-assets` #3500)、 **cloud-storage の object operation パラメータ設定** (#3529)。 修正は **GDA (Gemini Data Analytics) client の mTLS / `GOOGLE_API_USE_MTLS_ENDPOINT` 対応** (#3460、 AIP-4114 準拠で Context Aware Access(CAA) を回復)。 なお本リリースは 2026-06-26 新着で記録済みの未リリース dev (Dataplex/Looker tool 群、 #3337/#3478/#3494/#3507/#3531/#3515) を正式タグ化したもの。 [UPGRADING.md](https://github.com/googleapis/genai-toolbox/blob/main/UPGRADING.md) 参照。

#### 2026-07-01〜2026-07-07 新着 (v1.6.0 後の未リリース開発: Dataplex tool 続投 + ClickHouse vector)

- **ClickHouse SQL tool にネイティブ vector embedding 対応を追加** (#3229)
- **dataplex-create-data-product tool 追加** (#3504)、 **dataplex-get-data-asset tool 追加** (#3503)
- **parameters 堅牢化**: array/map 型エラーで問題の値を報告 (#3512)、 非 string 型フィールドで panic せずエラー返却 (#3516)
- **docs**: execute_sql の最小権限を明文化 (#3416)、 Announcement Banner 設定を追記 (#3532)
- **CI**: zizmor autofix (#3560)

#### v1.6.0 リリース (2026-06-30) の主要な変更点

前回記録点 `b67419d34` (= #3531) 以降で v1.6.0 タグまでに積まれた新規分。

**[Features]**

- **MCP 2026 draft spec サポート** (#3544): `vdraft` プロトコル実装 (manifests / method / types) を新設し `--enable-draft-specs` フラグで opt-in 有効化。 draft spec の正式リリースは暫定 2026-07-28 予定
- **`dataplex-get-data-product` tool 追加** (#3499): Dataplex data product を単体取得する tool
- **`dataplex-list-data-assets` tool 追加** (#3500): Dataplex data assets を列挙する tool
- **cloud-storage tool の object operation パラメータ設定** (#3529): object 操作パラメータを構成可能に

**[Security / Supply chain]**

- **Kokoro code signing を release workflow に統合しバイナリへ電子署名** (#3528): unsigned バイナリは unsigned GCS bucket へ、 署名済みは signed bucket へ分離アップロード + release table 生成時に署名済みバイナリを検証、 電子署名の検証手順をユーザガイドに追加 (issue #996)

**[Fixes]**

- **GDA (Gemini Data Analytics) client の mTLS / `GOOGLE_API_USE_MTLS_ENDPOINT` 対応** (#3460): 独自 REST HTTP client が動的 mTLS endpoint routing を欠き AIP-4114 違反 + Context Aware Access(CAA) を破壊していたのを修正。 `GOOGLE_API_USE_CLIENT_CERTIFICATE` / `GOOGLE_API_USE_MTLS_ENDPOINT` で endpoint を動的選択。 `bigquery-conversational-analytics` / `conversational-analytics-ask-data-agent` / `conversational-analytics-get-data-agent-info` / `conversational-analytics-list-accessible-data-agents` / `looker-conversational-analytics` を `NewGDAClient` 利用へ切替

**[Docs / deps]**

- **release 向け hugo 更新** (#3556)

破壊的変更なし (MCP draft spec は `--enable-draft-specs` opt-in で既定挙動不変、 code signing は release artifact のみ影響)。

#### 2026-06-26 新着 (v1.5.0 後の未リリース開発: Dataplex / Looker tool 群)

v1.5.0 後 main で 20 commits 進行（新リリースタグ未付与）。 主要なもの:

**[Features]**

- **`dataplex-list-data-products` tool 追加** (#3337): Dataplex data products を列挙する tool
- **cloud-storage tool の configurable parameters サポート** (#3478)
- **Looker: query の `dynamic_fields` パラメータサポート** (#3507)、 **複雑な `filter_expression` パラメータサポート** (#3494)

**[Fixes]**

- **Looker `explore_references` を panic でなく shape 検証に** (#3531)
- **`looker-create-view-from-table` の Looker API payload 構造修正** (#3515)

**[Refactor / 内部]**

- **`NewParameter` を functional-options パターンへリファクタ** (#3314)
- **config flag を cobra flag group 化** (#3477)、 **primitive の deprecation サポート追加** (#3327)

**[Docs / deps]**

- **SDK ページ（Python/JS/Go）を API reference サイトへリダイレクト** (#3505)、 CLI doc の sql-commenter flag 説明修正 (#3473)
- **langchain を v1.3.9 へ security bump** (#3469)、 Go update (#3393, #3471)、 GitHub Actions major (#3434)、 Hugo (#3317)

#### 2026-06-19 新着 (v1.5.0 リリース / SSRF guard 群 SECURITY / MCP auth ガード / MySQL tools)

**[Security]**

- **`source/http` に SSRF guard 実装** (#3448)
- **`source/cloudhealthcare`: pageURL パラメータ検証で SSRF 防止** (#3453)
- **`bigquery-execute-sql`: dataset restriction bypass を阻止** (#3452)
- **MCP auth と enable-api の同時有効化で fail させる** (#3435): 危険な構成をサーバ起動時に拒否

**[Features]**

- **MySQL / Cloud SQL MySQL 向け show-query-stats / list-all-locks tool 追加** (#2954)
- **HTTP transport の URL parameter binding 追加** (#3112)
- **Spanner: readOnly 設定時に read-only annotation を使用** (#3338)

**[Fixes]**

- **InitializeConfigs: panic でなく error を返却** (#3397)
- **auth/dataplex: service account credentials での source 失敗を修正** (#3369)
- **npm: バイナリバージョンを `cmd/version.txt` から取得** (#3417)
- **release 1.5.0 (#3379)** / hugo を release 向け更新 (#3479) / docsite version dropdown から v0.31.0 を除去 (#3481)

#### 2026-06-18 新着 (ScyllaDB source / Dataplex enrichment / query-plan injection 防止 / toolset filtering)

**[Features]**

- **ScyllaDB source / tool 追加** (#3119): ScyllaDB を source として新規サポート
- **Dataplex metadata enrichment workflow ツール** (#3270): metadata enrichment ワークフローを支援するツール群を Dataplex に追加
- **prebuilt CLI flag に toolset filtering サポート** (#3245): prebuilt CLI フラグで toolset フィルタリング可能に
- **SQL commenter の per-source level flags** (#3465): source レベルで SQL commenter フラグを有効化
- **bigquery `maximumBytesBilled` を prebuilt config に配線** (#3385)
- **config parse error に doc / line context 追加** (#2957)

**[Security]**

- **SECURITY: mysql-get-query-plan の query 実行バイパス + statement injection 防止** (#3235): `mysql-get-query-plan` ツールで query 実行バイパスと statement injection を防止
- **SECURITY: cloud-storage source の bucket / local path アクセス制限** (#3454): bucket と local path のアクセスを制限
- **SECURITY: auth/google で mcpEnabled 時に audience か clientId を必須化** (#3450)
- **fix(deps): JS doc サンプルの npm audit 脆弱性パッチ** (#3442)

**[CI / docs / deps]**

- **OSS Exit Gate 経由の publish 自動化**: npm publishing (#3391) / PyPI publishing (#3430) を自動化、 npm `.npmrc` を `$HOME` に書き `--registry` を npm publish に渡す修正 (#3431)、 npm major updates を per-dependency PR に ungroup (#3427)
- **docs**: cloud-run の VPC 設定明確化 (#3414)、 SQL commenter と telemetry attributes (#3458)、 readme に mariadb 追加 (#3242)
- **integration test skip 修正と core pattern 集約** (#3401)、 **wontfix ラベル追加** (#3470)
- **JS quickstart 依存バンプ**: langchain 1.2.12 → 1.3.9 (#3467)、 @google/adk ^1.2.0 (#3428, #3436)、 @google/genai ^2.8.0 (#3438)、 ws 8.20.1 → 8.21.0 (#3466, #3432)、 form-data 4.0.5 → 4.0.6 (#3468, #3433)

#### 2026-06-15 新着 (regex method injection / path normalization bypass パッチ)

- **SECURITY: picomatch を bump**: regex method injection を解消するため picomatch を 2.3.2 (#3426) / 4.0.4 (#3429) にバンプ
- **SECURITY: fast-uri 3.1.2 へ bump**: path normalization bypass を解消するため fast-uri を 3.1.2 に (#3425)
- **docs quickstart 依存バンプ群**: fast-xml-parser 5.5.x → 5.9.0 (#3424, #3421)、 hono 4.12.x → 4.12.25 (#3422, #3361)、 axios 1.15.0 → 1.18.0 (#3420, #3419, #3418)、 qs / express (#3282, #3309)、 ip-address / express-rate-limit (#3423)、 @grpc/grpc-js 1.14.3 → 1.14.4 (#3404) を各 ADK / genkit / langchain quickstart で bump

#### 2026-06-12 新着 (SQL injection escape / MCP HTTP body size 制限)

- **SECURITY: `applyEscape` で delimiter 文字を escape**: SQL injection を防ぐため `applyEscape` で区切り文字を escape (#2811)。 関連して bigquery_integration_test.go の escape も更新 (#3392)
- **SECURITY: MCP HTTP body size を制限**: MCP の HTTP body サイズに上限を設定 (#3216)
- **tool 初期化を source から decouple**: tool の初期化を sources から切り離し (#3355)
- **skills のオフライン生成**: live source 接続なしで skills を生成可能に (#3388)、 オフライン skills-generate 時に未設定 env var を許容 (#3399)
- **dataplex / datalineage の default credentials に cloud-platform scope 指定** (#3376)
- **alloydb-omni prebuilt で password env var を明示必須化** (#3398)
- **依存バンプ**: go update (#3310)、 `@grpc/grpc-js` 1.14.3 → 1.14.4 (#3402)

#### v1.4.0 の主要な変更点（2026-06-04）

- **Data Lineage 統合**: Data Lineage integration を追加 (#3285)
- **`--ignore-unknown-tools`**: 起動時に未知ツールを無視するフラグ (#3353)
- **Cloud SQL PG vector assist tools**: 残りの vector assist tools を追加 (#3203)
- **Spanner `search_catalog`**: search_catalog tool を実装 (#3140)
- **opaque token の issuer 必須化**: generic auth の opaque token validation で issuer presence を強制 (セキュリティ) (#3360)
- **Google / Generic MCP OAuth 検証の分離**: OAuth verification を分離 (セキュリティ) (#3341)
- **windows/arm64 バイナリ配布**: CI で windows/arm64 をサポート (#3231)

#### v1.3.0 以降の変更点（v1.4.0 に取り込み済み）

- **ClickHouse / BigQuery identifier injection 防止**: identifier パラメータをバリデーションし injection を防止 (セキュリティ) (#3219)
- **apache/thrift CVE-2026-41602 対応**: apache/thrift を v0.22.0 → v0.23.0 に置換し CVE を解消 (#3312)
- **Looker unquoted parameters filter value escape**: unquoted パラメータの filter 値をエスケープ (#3289)
- **GitHub Actions メジャーアップデート**: GitHub Actions 群を major バージョン更新 (#3316)
- **Go ランタイム更新**: go の更新 (#3187)
- **conformance presubmit go version mismatch 修正**: presubmit の go version mismatch を修正 (#3315)
- **依存バンプ群**: otel 1.39.0 → 1.41.0 (#3198)、 fast-xml-builder 1.1.4 → 1.2.0 (#3200)、 brace-expansion (#3246)、 ws 8.19.0 → 8.21.0 (#3248) / 8.18.3 → 8.20.1 (#3262)

#### v1.3.0 の主要な変更点（2026-05-21）

**[Features]**

- **`cloud-sql-admin-execute-sql-many` / `cloud-sql-admin-sql-many` ツール追加**: Cloud SQL admin 系で bulk execute-sql / sql ツールを新規追加 (#3083)
- **SQLCommenter + クライアントメタデータ送出**: SQL に client metadata コメントを付与する SQLCommenter 機構を追加 (#3064)
- **MCP auth tool-level scopes バリデーション**: tool レベルの scope を MCP auth でバリデーション (#3049)
- **Looker client IP 伝搬**: incoming MCP リクエストの client IP を downstream SDK 呼び出しに伝搬 (#3253)

**[Bug Fixes]**

- **HTTP tool path traversal / base path scope escape 防止**: HTTP tool での path traversal と base path scope escape を防止 (セキュリティ) (#3218)
- **toolset/promptset boundary 強制**: `tools/call` と `prompts/get` で toolset/promptset の境界を強制 (#3036)
- **generic auth expiration 修正**: generic auth の expiration フィールドと `authRequired` の統合を修正 (#3251)
- **Looker 401 透過**: Looker が 401 を返した場合 MCP クライアントに 401 をそのまま返却 (#3233)
- **Looker filter value wrapping quotes strip**: unquoted パラメータの filter 値から囲み quote を除去 (#3273)
- **query result slices 初期化**: query 結果スライスを空配列で初期化 (#3250)

#### v1.2.0 の主要な変更点（2026-05-07）

**[Features]**

- **HTTPS/TLS listener 対応**: HTTPS/TLS listener サポート追加 (#3126)
- **BigQuery `maximumBytesBilled` ソース設定**: BigQuery source にコスト制限用の `maximumBytesBilled` 設定追加 (#2724)
- **Cloud Storage source (read 系)**: `list_objects`, `read_object` ツールを提供する Cloud Storage source を新規追加 (#3081)
- **Cloud Storage bucket / object 管理ツール**: bucket and object 管理ツールを Cloud Storage source に追加 (#3129)
- **Cloud Storage write/copy/move/delete object ツール**: Cloud Storage source に write/copy/move/delete 操作を追加 (#3139)
- **Knowledge-catalog Data Quality Scans 検索**: スキャン ID・テーブル名フィルタ、 pagination、 sort 対応の Dataplex DQ Scans 検索ツール (#2444)

**[Bug Fixes]**

- **string literal block with list 変換許可**: 該当変換を許可 (#3050, closes #3023)
- **MCP router-level logger injection 実装**: MCP auth で router-level logger injection (#3067)
- **test.db 生成防止**: unit test 中の test.db 生成を防止 (#3042)
- **SSE hardcoded `*` allowed origin 削除**: SSE の hardcoded allow-origin を削除 (セキュリティ) (#3054)
- **Postgres ソース URL エンコーディング修正**: query string params の URL encoding 適用 (#3020)
- **Looker conversational-analytics OAuth トークン**: GDA payload で OAuth token を修正 (#3058)
- **BigQuery execute-sql エラー出力**: 不正クエリを MCP 500 として表面化しないよう修正 (#3056)
- **Looker Conversational Analytics OAuth**: Looker Conversational Analytics 向け OAuth 修正 (#3044)

#### v1.1.0 の主要な変更点

- **Cloud SQL Postgres vector assist ツール**: Cloud SQL Postgres 向けベクターアシストツール追加 (#2909)
- **Looker YAML フラット化**: Looker 設定 YAML をフラット形式に変換修正 (#3022)
- **dataplex → knowledge-catalog リネーム**: ドキュメント全体で dataplex を knowledge-catalog にリネーム (#3039)

#### v1.0.0 の主要な変更点（**安定版リリース**）

- **Elasticsearch vector search**: ベクターサーチサポート追加＆クエリパススルーパラメータ削除（**破壊的変更**） (#2891)
- **Looker git-branch ツールリファクタ**: looker-git-branch ツールを5つの個別ツールに分割（**破壊的変更**） (#2976)
- **opaque token バリデーション**: `generic` authService での opaque token バリデーションサポート (#2944)
- **Cloud SQL Postgres 接続確認**: 接続成功後に `SELECT 1` を実行 (#2997)
- **BigQuery semantic search**: BigQuery SQL にセマンティックサーチサポート追加 (#2890)
- **Elasticsearch ES/QL**: 任意の ES/QL クエリ実行ツール追加 (#3013)
- **MySQL list-table-stats**: MySQL テーブル統計一覧ツール追加 (#2938)

#### v0.32.0 の主要な変更点

- **リポジトリ名更新**: リポジトリ名の変更（**破壊的変更**） (#2968)
- **MCP ツールアノテーション**: 全残ツールに MCP ツールアノテーション追加 (#2221)
- **BigQuery 会話分析ツール**: Data Agents 向け会話分析ツール追加 (#2517)
- **Claude Code / Codex スキルサポート**: 生成スクリプトに Claude Code と Codex user agent サポート追加 (#2966, #2973)
- **npx 経由ツール実行**: npx でのツール呼び出しサポート (#2916)
- **Looker エージェント管理**: MCP からの Looker エージェント管理 (#2830)

#### v0.31.0 の主要な変更点

- **`enable-api` フラグ**: API 有効化フラグの追加（**破壊的変更**）
- **Protected Resource Metadata エンドポイント**: Protected Resource Metadata エンドポイント追加
- **Manual PRM オーバーライド**: 手動 PRM オーバーライドサポート
- **Dataplex ルックアップコンテキストツール**: Dataplex ルックアップコンテキストツール追加
- **非推奨項目削除＆tools-file フラグ更新**: 非推奨項目の削除（**破壊的変更**）

#### 破壊的変更

| 変更 | 影響 |
|------|------|
| Elasticsearch vector search (v1.0.0, #2891) | クエリパススルーパラメータ削除 |
| Looker git-branch リファクタ (v1.0.0, #2976) | 1ツール → 5ツールへの分割 |
| リポジトリ名更新 (v0.32.0, #2968) | リポジトリ URL の変更 |
| `enable-api` フラグ (v0.31.0) | API エンドポイントの明示的有効化が必要 |
| 非推奨項目削除 (v0.31.0, #2806) | tools-file フラグ等の変更 |
| HTTP 非 2xx エラー出力サニタイズ (v0.31.0, #2654) | エラーレスポンス形式変更 |
| プリビルトツールセット再構成 (v0.29.0) | AlloyDB, Spanner 等のツールセット構造変更 |
| 設定ファイル v2 (v0.27.0, #2369) | 設定ファイルフォーマットの変更が必要 |

#### 参考リンク

- [GenAI Toolbox](https://github.com/googleapis/genai-toolbox)

---

### Knowledge Catalog

**現行バージョン**: 継続的デプロイ（バージョンタグなし、 新規追跡開始）

**チェックアウト状態**: `d44368c` (main HEAD、 2026-06-20。 OKF 中心へのリポ再構成 + ConversationLearner 一連を含む)

**管理**: Google Cloud Platform（公式 Google 製品ではない sample/tools リポ）

**注目**: **Knowledge Catalog（旧 Dataplex）** = AI-powered な data catalog / metadata management プラットフォーム。 構造化・非構造化データの dynamic knowledge graph を提供し、 AI エージェントに semantics と business context を与える。 本リポは Knowledge Catalog 機能のデモ、 ツール、 そして **context management / enrichment / retrieval** ソリューション構築用の **samples / tools** を収録。 GenAI Toolbox 側の **dataplex → knowledge-catalog リネーム** (#3039) や Cloud SQL / BigQuery 系 DQ Scans 検索ツール (#2444) と同じ「Dataplex 改め Knowledge Catalog」軸に連なる。 **2026-06-20 にリポを Open Knowledge Format (OKF) 中心へ再構成**: トップレベルの `agents/` フォルダを撤去し、 enrichment agent を `okf/src/reference_agent` へ統合（旧 `enrichment_agent` → `reference_agent` にリネーム）。 現構成は `okf/`（OKF reference 実装 + reference_agent）/ `samples/`（discovery, enrichment）/ `toolbox/`（enrichment, mdcode）。

#### 2026-06-20 新着 (OKF 中心へ再構成 / reference_agent リネーム / ConversationLearner agent)

- **OKF 中心へリポ再構成**: README タイトル / intro を format（OKF）に焦点化 (#130)、 `enrichment_agent` パッケージを `reference_agent` にリネーム (#129)、 トップレベル `agents/` フォルダを撤去 (#128)
- **ConversationLearner agent 追加** (#105): 会話ログから知識を学習する agent を新設。 続けて per-conversation 並列分析 + dedup (#114)、 `page_size=1000` でのログ取得 (#116)、 optional stable proposal IDs (#117)、 human-in-the-loop proposal review UI（ローカル）(#118)、 non-interactive CLI entrypoint (#126)、 cross-conversation recurrence aggregation (#127) を追加
- **enrichment agent: Confluence / SharePoint source + OKF 出力** (#106, #108)、 **cross-cutting hybrid KB / per-entry table fact_recall / public goldens** (#103)

#### 主要な構成

- **Open Knowledge Format (OKF)**: メタデータを **metadata-as-code** で扱う reference 実装（`okf/`）。 OKF demo（GA4 demo 含む #19）、 Dataplex 上の Documents Layout を parent でリンク (#24)、 OKF cross-links を file-relative パス化し GitHub 上で bundle がレンダリングされるよう修正 (#45)。 reference agent は `okf/src/reference_agent`（旧 `enrichment_agent` をリネーム・統合 #129）
- **enrichment agent (ADK ベース)**: 旧 `agents/enrichment`（現 `samples/enrichment` + `toolbox/enrichment`）に enrichment agent + evaluation harness を sync (#42)、 OKF reference enrichment agent を import (#28)、 financial_services / phone_services コーパスでの eval corpora を同梱
- **onboarding 整備**: agent `requirements.txt` 追加と onboarding ドキュメント改善 (#54)

#### 参考リンク

- [knowledge-catalog (GitHub)](https://github.com/GoogleCloudPlatform/knowledge-catalog)
- [Knowledge Catalog (Google Cloud)](https://cloud.google.com/products/knowledge-catalog)

---

## 注目ポイント

### 破壊的変更一覧

| 対象 | 変更内容 | 対応優先度 |
|------|---------|-----------|
| **MCP 2026-07-28-RC stateless 化** (draft, 2026-07 未確定) | initialize handshake 撤廃・per-request メタ化 (SEP-2575)、 `Mcp-Session-Id` 廃止 (SEP-2567)、 server-initiated request → MRTR (SEP-2322)、 `subscriptions/listen` 導入、 `ping`/`logging/setLevel` 削除、 error code `-32002`→`-32602`。 **RC/draft 段階だが finalize されると接続モデルが根本的に変わる** | 高 |
| **ADK Python v2.5.0 OTel Events API 削除** (2026-07-16) | OpenTelemetry Events API/SDK deprecation に伴い event logger setup を削除。 Events API 経由の telemetry 設定が無効化 | 中 |
| **UCP `keys[]` を canonical 署名鍵フィールドに昇格** (#566, 2026-07-12) | profile の署名鍵参照方法が変更、 旧フィールド利用側は移行必要 | 中 |
| **ADK Python telemetry メトリクス削除・改名** (main, 2026-07 未リリース) | `gen_ai.agent.workflow.steps` / `gen_ai.agent.{request,response}.size` を削除、 duration メトリクスを GenAI semconv 名へ改名。 既存 OTel ダッシュボード / アラートの見直しが必要 | 中 |
| **UCP 名前空間権限バインディング規範化** (#530, 2026-07-03) | 宣言スキーマ URL → 逆ドメイン権限の束縛手順を新規に厳密化（https 必須・userinfo 拒否・登録ドメイン要求）。 矛盾していた規範文の統一のため、 既存実装は検証手順の適合確認が必要 | 中 |
| **ADK Go v2.0.0** (2026-06-30) | module path 変更 `google.golang.org/adk` → `/v2`、 `session.NewEvent` の `context.Context` 必須化、 ToolContext/CallbackContext の統一 Context 統合、 `InvocationContext.TriggeredBy()` 削除。 `workflow` パッケージ新規導入が柱。 1.x は `v1` ブランチで継続メンテ | 高 |
| **AG-UI Mastra 標準 interrupt-outcome 既定 ON 化** (#2059, 未リリース main) | `emitInterruptOutcome` が既定 TRUE (opt-out) に。 **CopilotKit client >= 1.61.2 必須**（未満だと run が stranded） | 中 |
| **ADK Python Anthropic effort/thinking 設定** (main, 2026-06-29〜) | `AnthropicGenerateContentConfig` 導入に伴い、 従来 Claude で無視されていた temperature/top_p/top_k/stop_sequences/max_output_tokens が client へ伝播するように。 `max_output_tokens` が既定 max_tokens=8192 を上書きする | 中 |
| **ADK JS v1.3.0** (2026-06-22) | v1.2.0 後 main の Skills Registry 3部作 / OpenAPI REST tool part 3 / integrations package / `--reload_agents` を正式リリース。 **破壊的**: dev server デフォルトポート 8000 → 8080 (#439)、 Agent Engine デプロイ先 GCR → Artifact Registry (#441) | 高 |
| **UCP fulfillment methods を catalog へ** (#507, 2026-06-26) | `feat!` で fulfillment を catalog surface (search/lookup/get_product) に合成、 checkout の `type` enum を open vocabulary 化、 destinations を単一形状へ。 method-first discovery への移行 | 中 |
| **AG-UI .NET SDK 新設 + langgraph>=0.6.0** (release/2026-06-24) | C#/.NET フル SDK (0.1.0-preview) を新規追加 (#1963)。 langgraph structured interrupt/resume サポートで **`langgraph>=0.6.0` を必須化**（opt-in、 default off, #1945） | 中 |
| **ADK Python v2.3.0** (2026-06-19) | v2.x 次期リリースを main にマージ。 **SECURITY: Filename 経由の Code Generation Template Injection 修正**、 A2A `_serialize_value()` の JSON-native 型保持、 tuple tool parameters サポート、 LiteLLM Claude thinking blocks 修正、 instruction util リファクタ rollback（internal customers を壊すため） | 高 |
| **GenAI Toolbox v1.5.0** (2026-06-19) | **SECURITY 強化リリース**: `source/http` SSRF guard (#3448)、 cloudhealthcare pageURL SSRF 防止 (#3453)、 bigquery dataset restriction bypass 阻止 (#3452)、 MCP auth + enable-api 同時有効化 fail (#3435)。 機能面は MySQL show-query-stats / list-all-locks (#2954)、 HTTP URL parameter binding (#3112) | 高 |
| **AG-UI パッケージリリース群** (release/2026-06-19) | @ag-ui/a2ui-middleware 0.0.10、 @ag-ui/aws-strands + ag_ui_strands 0.2.1、 @ag-ui/langgraph + ag-ui-langgraph 0.0.42。 ADK へ A2UI sub-agent rendering tool 移植 (OSS-158)、 google-adk floor を 1.28.1 へ・`<3.0` 許可（`<2.0` cap 撤廃） | 中 |
| **A2UI v1.0 Text component heading variants 削除** (#1668, 2026-06-17) | `spec(v1.0)!` で Text コンポーネントの冗長 heading variant を除去（後方互換破壊）。 同時に v1.0 catalog の JSON Schema 制約を厳格化 + 統合 (#1629) | 中 |
| **UCP buyer consent per-segment** (#451, 2026-06-12) | `feat!` で buyer consent を per-segment extensibility 化し後方互換を破る。 delegated identity providers + accelerated IdP flow (#423) も同梱 | 中 |
| **A2UI v0.10 → v1.0 spec 昇格 + inline catalog instructions** (#1590, 2026-06-12) | 次期 spec が `specification/v1_0` へ昇格。 catalog instructions を相対 file URI から inline Markdown へ (BREAKING)、 `instructions.md` を廃止 | 中 |
| **ADK Python telemetry metrics 単位変更** (main, 2026-06-13) | agent / tool 実行時間メトリクスを ミリ秒 → 秒 へ変更。 既存 OTel ダッシュボード / アラート閾値の見直しが必要 | 中 |
| **ADK Python v2.2.0** (2026-06-04) | Google GenAI SDK v2.0.0 対応、 AutoTracingPlugin、 RubricBasedMultiTurnTrajectoryEvaluator、 path traversal / Zip Slip / unpickle 制限 / CVE-2026-48710 等のセキュリティ修正一括 | 高 |
| **ADK JS v1.2.0** (2026-06-03) | v1.1.0 後のセキュリティ修正（CORS、 OAuth2 SSRF、 host 制限）を取り込み。 後続 main で Skills Registry 3部作 + streaming prototype pollution 修正 | 高 |
| **GenAI Toolbox v1.4.0** (2026-06-04) | Data Lineage 統合、 `--ignore-unknown-tools`、 identifier injection 防止 / opaque token issuer 必須化 / OAuth 検証分離（セキュリティ） | 中 |
| **A2UI v0.10 `theme` → `surfaceProperties`** (#1525, 2026-06) | BREAKING rename + `primaryColor` 削除。 v0.10 では surfaceId の client session 毎グローバル一意化 (#1543) も | 中 |
| **A2UI v0.10 MIME 変更** (#1493, 2026-06) | IANA 規約準拠で mime type を `application/a2ui+json` へ変更（POTENTIALLY BREAKING）。 既存 A2UI-over-HTTP / MCP クライアントの content-type 判定に影響 | 中 |
| **MCP-Apps v1.7.4 PKCE 必須化** (#681, 2026-06-04) | lazy-auth-server の token exchange で PKCE を必須化し redirect_uri をバインド（セキュリティ強化）。 PKCE 非対応の旧フローは拒否される。 base path 配下マウントも対応 (#683) | 中 |
| **ADK Go v1.4.0** (2026-05-29) | Context unification（tool context を callbackContext にマージする内部統合）、 adka2a structured error propagation、 examples / CLI を a2a-go/v2 SDK へ移行、 metadata-only SSE チャンク許容でストリーム中断防止 | 高 |
| **GenAI Toolbox v1.3.0** (2026-05-21) | `cloud-sql-admin-execute-sql-many` / `sql-many` bulk ツール、 SQLCommenter（client metadata 送出）、 MCP auth tool-level scopes バリデーション、 HTTP tool path traversal 防止（セキュリティ） | 中 |
| **GKE MCP v0.13.0** (2026-05-28) | k8s リソース操作ツール群（apply / get / describe / patch / delete / logs / rollout / auth / api-resources / cluster-info / events）一括拡充、 install checksum verification、 insecure `pull_request_target` 防止 CI | 中 |
| **Google Analytics MCP 0.6.0** (2026-05-21) | subprocess stdio handle inheritance 防止（v0.4.0 #151 のフォローアップ deadlock 解消, #154）を正式リリース | 低 |
| **ADK Python v2.0.0 GA** (2026-05-19) | v1.x → v2.0 メジャー昇格。 Multi-Agent Workflow Engine / Flexible Execution Graphs / Intelligent Task Delegation / Native Inter-Agent Routing が production-grade GA に。 main ブランチも v2.0.0 へ transition。 v1.34.0 は LTS として継続。 直近 HEAD で v2 リリースワークフローを v1 ブランチへ repoint | 高 |
| **ADK Go v1.3.0** (2026-05-20) | Live bidirectional streaming のコア機能（session resumption / streaming tools / audio cache）一括取り込み、 a2a-go/v2 互換化、 VertexAI MemoryBank サポート、 `gen_ai.usage` 属性 rename (OTel 整合) | 高 |
| **Agent Starter Pack maintenance mode** (2026-05-21) | README で **公式に maintenance mode を surface**、 後継 **agents-cli** への移行を push (#967)。 新規プロジェクトは agents-cli を使うべき | 高 |
| **UCP loyalty extension** (#340, v2026-04-08 後) | catalog / cart / checkout capability に loyalty 拡張を追加。 既存 discount 拡張に続く 2 つ目の正式拡張 | 中 |
| **UTCP v1.0** (新規追跡, 直近 commit 2026-05-05) | MCP の構造的代替案（agent → native endpoint 直叩き）、 plugin architecture へ全面再設計 | 中 |
| **Visa Trusted Agent Protocol** (新規追跡, `payments/`) | Agentic commerce での agent identity / authorization 標準。 cryptographic signature ベース | 中 |
| **Mastercard Verifiable Intent v0.1.0** (新規追跡, 2026-03-05 OSS化, `payments/`) | SD-JWT chain で user → agent delegation scope を verify、 Selective Disclosure でプライバシー保護 | 中 |
| **Gemini Cloud Assist MCP v0.8.0** (新規追跡, 2026-04-21) | Local Node.js → Remote MCP Server へ全面刷新、 v0.2.0 (local) は完全 deprecate | 高 |
| **ADK Python v1.34.0** (2026-05-18) | a2a persistent task stores、 Gemini Live API in ADK evaluate、 mTLS Cloud Telemetry exporter、 GCPSkillRegistry / Skill Registry 実装、 McpToolset OAuth PKCE | 高 |
| **ADK Python v1.33.0** (2026-05-08) | BufferableSessionService、 LlmResponse function call/response ヘルパー、 ApigeeLlm credential 注入、 adk web hot reload | 中 |
| **GenAI Toolbox v1.2.0** (2026-05-07) | Cloud Storage source write/copy/move/delete、 HTTPS/TLS listener、 BigQuery `maximumBytesBilled`、 Knowledge-catalog DQ Scans 検索 | 中 |
| **MCP SEP-2567/SEP-2575** (2025-11-25 後) | Sessionless MCP via Explicit State Handles + Make MCP Stateless、 ステートレス志向への大型仕様シフト | 高 |
| **ACP v2026-04-17 後 #429 (UCP)** | UCP の profile schemas 検証修復は破壊的、 既存実装の再検証必要 | 中 |
| **UCP v2026-04-08 後** | Identity Linking OAuth 2.0 foundation、capability-driven scopes（破壊的）、 profile schemas 検証修復（#429、 破壊的） | 高 |
| **MCP-UI v7.1.1** (2026-05-09) | sandbox proxy iframe timeout cancel で StrictMode 安定化、 v7.1.0 の hostInfo/hostCapabilities props と組合せ | 中 |
| **ADK Python v1.32.0** (2026-04-30) | SSRF / RCE / credential isolation 等のセキュリティ修正、Anthropic thinking blocks、native OTel agentic metrics | 高 |
| **GKE MCP v0.12.0** | Anthropic Claude ADK adapter、node pool 管理ツール、新規 cluster ツール群 | 中 |
| **Google Analytics MCP 0.5.0** | conversions schema/spec ツール、 v0.4.0 では tool call deadlock 修正・`run_funnel_report` ツール・ADK Skills 追加 | 中 |
| **AP2 v0.2.0** (2026-04-28) | V2 仕様正式リリース。v0.1.0 から 7 ヶ月ぶりの大型更新 | 高 |
| **gcloud-mcp storage-mcp v0.6.0** (2026-05-06) | `download_object_safe` ツール削除（破壊的変更）。 destructive 経路 `download_object` または `read_object_content` / `read_object_metadata` への移行必須 | 中 |
| **ADK JS v1.0.0 → v1.1.0** | UrlContextTool/Vertex AI Search Tool 追加、MCP プレフィックス strip 修正、AgentTool セッション再利用 | 中 |
| **ADK Go v1.2.0** | Agent Engine 統合、Skill Source proxy 群、SkillToolset 実装、stream_query simple text サポート | 中 |
| **UCP v2026-04-08** | 6件の破壊的変更: variant options リネーム、webhook 分離、エラー統一、currency 必須化等 | 高 |
| **GenAI Toolbox v1.0.0** | Elasticsearch vector search リファクタ、Looker ツール分割 | 高 |
| **GenAI Toolbox v0.32.0** | リポジトリ名更新 | 高 |
| **GenAI Toolbox v0.31.0** | `enable-api` フラグ必須化、非推奨項目削除 | 高 |
| **A2A v1.0.0** | Push Notification Config 統合、`blocking`→`return_immediately`、仕様リファクタ | 高 |
| **MCP-UI v7.0.0** | レガシー仕様の完全削除 | 高 |
| **ACP v2026-01-30** | Payment Handlers Framework 導入 | 高 |
| **MCP-Apps v1.7.0** | ツール登録 WebMCP-style 仕様化、Zod jitless デフォルト化 | 中 |
| **x402** | メインリポジトリが foundation repo へ移動 | 中 |
| **ADK Python v1.29.0** | SecretManagerClient パッケージ移動 | 中 |
| **Google Analytics MCP** (未リリース) | パッケージ名 `analytics-mcp` にリネーム | 低 |

### メジャーアップデート

**― 2026-07-18 更新分 (submodule remote HEAD 追従) ―**

0. **NEW: MCP 2026-07-28-RC draft が stateless 化へ** - RC/draft 段階で、 initialize handshake 撤廃・session 廃止・`server/discover`・`subscriptions/listen`・MRTR (server-initiated request 廃止) 等の大型破壊的変更が landing (SEP-2575/2567/2322)。 finalize 前だが接続モデルの根本変更に注意
0. **NEW: ADK Python v2.5.0** (2026-07-16) - ManagedAgent (single_turn/remote MCP)、 Skill/Agent Registry (`GCPSkillRegistry`)、 Workflow resumability/HITL、 mTLS 全面化。 **破壊的**: OTel Events API 削除。 adk-go v2.0.0 と同一の Multi-Agent Workflow GA 路線
0. **NEW: GenAI Toolbox v1.7.0** (2026-07) - ArcadeDB source/tools、 Dataplex data-product tool 拡充、 ClickHouse native vector embedding、 quotaProject 対応。 破壊的変更なし
0. **NEW: A2UI v1.0 RC 加速** (2026-07、 71 commits) - 同期 client→server RPC / `callFunction` / createSurface 一括生成。 **破壊的 (v1.0 RC vs v0.9)**: `theme`→`surfaceProperties`、 MIME `application/a2ui+json`、 catalog `functions` map 化。 production は v0.9.1
0. **NEW: ADK Go v2.0.0 後 / ADK JS v1.3.0 後 (未リリース)** - Go: `agentregistry` package + provider auth + MCP per-request auth (+24 commits)。 JS: Gemini Interaction API (#364) + Agent-Controlled Compaction (#477) + Skills Registry + OpenAPI REST tool (+28 commits)
0. **NEW: Cloud Run MCP Docker Compose デプロイ (未リリース)** - `deployCompose` capability で compose 定義から Cloud Run へ直接デプロイ、 volume/Secret Manager/AI models 対応、 Cloud Build 統合 (#252 ほか)
0. **NEW: UCP `keys[]` 昇格 (破壊的, #566, 2026-07-12)** - profile 署名鍵フィールドを canonical 化。 Web Bot Auth interop + per-operation Requirement 列も
0. **NEW: OpenResponses WebSocket transport + compaction** - `/v1/responses` に WebSocket モード (#71/#72)、 `POST /v1/responses/compact` (#68)、 spec の日付版バージョニング導入 (#77)
0. **NEW: webmcp-tools v0.0.3** (2026-07-17) - Page Agent 向け `execute_batch` "Code Mode" (#287)、 WebMCP Polyfill (#276)、 Backend に Gemini/Ollama (#294)

**― 以下は 2026-07-10 以前の記録 ―**

0. **NEW: ADK Python v2.4.0 / v1.36.1 タグ発行** (2026-07-07 / 07-06) - release ブランチ上でタグ発行（mirror main へは CHANGELOG 未反映、 詳細内訳は次窓で確認）。 main 側は Workflow as Tool / ManagedAgent / DaytonaEnvironment / mTLS 拡大 / artifact 越境防止・DNS rebinding 保護（セキュリティ）等 +67 commits
0. **NEW: GKE MCP v0.14.0** (2026-07-06) - `verify_unused` クラスタ安全性チェック skill / TPU dynamic slices 監視・管理 skill / query_logs View パラメータ (BASIC|FULL)。 依存で adk 1.5.0 と adk-anthropic-go 1.0.0（メジャー）へ
0. **NEW: AG-UI mastra@1.1.0/1.1.1 リリース** (2026-07-02 / 07-03) - Mastra interrupt/resume 整備の正式タグ化。 Observational Memory の activity event 化 (OSS-92)、 shared-state リモートパリティ (OSS-414)、 tracingOptions パススルー (#2083)。 sdk-dotnet AGUI.\* 0.0.3（NuGet リリース対応）も同窓
0. **NEW: UCP Web Bot Auth 相互運用 + 名前空間権限バインディング** (2026-07-02/03) - EdDSA (Ed25519) をオプション署名アルゴリズムに追加（WBA interop 選択時は MUST、 #483）、 スキーマ URL → RDNS 権限の束縛手順を規範化 (#530)
0. **NEW: ADK Go v2.0.0** (2026-06-30) - **メジャーリリース**。 module path を `google.golang.org/adk` → `/v2` へ変更（破壊的）。 `workflow` パッケージを新規導入（scheduler ベースの goroutine-per-node 実行エンジン、 HITL の pause/resume・handoff/re-entry モード、 JoinNode fan-in、 547 files の巨大 squash、 #1109）。 `session.NewEvent` の context 必須化、 ToolContext/CallbackContext 統一、 `InvocationContext.TriggeredBy()` 削除も同時破壊的変更。 1.x は `v1` ブランチで継続メンテ、 直前に v1.5.0 も同日リリース
0. **NEW: GenAI Toolbox v1.6.0** (2026-06-30) - **MCP 2026 draft spec サポート追加** (#3544、 `--enable-draft-specs` opt-in、 正式リリース暫定 2026-07-28 予定)。 **Kokoro code signing を release workflow に統合しバイナリへ電子署名** (#3528、 issue #996 対応)。 Dataplex data-product 系 tool 拡充 (#3499, #3500)、 GDA client の mTLS/CAA 対応修正 (#3460)。 破壊的変更なし
0. **NEW: AG-UI Mastra interrupt/resume 一斉整備** (main, 2026-07-01、 未リリース) - native `useInterrupt` suspend/resume、 標準 interrupt-outcome 既定 ON 化（**破壊的、 CopilotKit client >= 1.61.2 必須**、 #2059）、 remote agent resume 対応、 background task の activity event 化、 tool-call args 逐次ストリーミング。 いずれも新規 release タグは未発行
0. **NEW: ADK JS v1.3.0** (2026-06-22) - v1.2.0 後 main で進めていた **Skills Registry 3部作**（Core + GCP remote + 動的 SearchSkillsTool、 #422-424）、 **OpenAPI REST API tool (part 3、 #386)**、 **新規 integrations package (#449)**、 **`--reload_agents` hot-reload (#304)**、 **Gemini 2.5/3.x Live Models (#409)** を正式リリース。 セキュリティは streaming prototype pollution 修正 (#410)。 **破壊的**: dev server デフォルトポート 8000 → 8080 (#439)、 Agent Engine デプロイ先を GCR → Artifact Registry へ (#441)
0. **NEW: AG-UI .NET SDK 新設 + langgraph structured interrupt/resume** (release/2026-06-24) - **C#/.NET 向けフル SDK (0.1.0-preview)** を新規追加 (#1963): `AGUI.Abstractions` / `.Formatting` / `.Client` / `.Server` / protobuf transport / OTel tracing / クロス言語テストハーネス。 langgraph に **structured interrupt/resume**（opt-in、 `langgraph>=0.6.0` 必須、 #1945）、 DeepSeek `reasoning_content` 対応 (#1256)、 stable messageId 再利用 (#1317)。 ag_ui_adk 0.7.0 / aws-strands 0.2.3 へ
0. **NEW: ADK Python v2.3.0** (2026-06-19) - v2.x 次期リリースを main にマージ。 **SECURITY: Filename 経由の Code Generation Template Injection 修正**が目玉。 A2A `_serialize_value()` の JSON-native 型保持・コンテナ再帰、 tuple tool parameters サポート、 `safe_json_serialize` での Pydantic モデル処理、 LiteLLM Claude thinking blocks (`display:"omitted"`) 修正、 GcsArtifactService の `file_data` URI 参照、 instructions_utils の placeholder / nested path マッチング修正（internal customers を壊す instruction util リファクタは rollback）
0. **NEW: GenAI Toolbox v1.5.0** (2026-06-19) - **SSRF guard 強化リリース** (#3379)。 `source/http` SSRF guard (#3448)、 `source/cloudhealthcare` pageURL 検証 (#3453)、 `bigquery-execute-sql` dataset restriction bypass 阻止 (#3452)、 MCP auth + enable-api 同時有効化 fail (#3435)、 InitializeConfigs panic → error 化 (#3397)。 機能面は MySQL / Cloud SQL MySQL の show-query-stats / list-all-locks (#2954)、 HTTP transport の URL parameter binding (#3112)、 Spanner readOnly annotation (#3338)
0. **NEW: AG-UI パッケージリリース群** (release/2026-06-19) - @ag-ui/a2ui-middleware 0.0.10 / @ag-ui/aws-strands + ag_ui_strands 0.2.1 / @ag-ui/langgraph + ag-ui-langgraph 0.0.42。 **ADK へ A2UI sub-agent rendering tool 移植 (OSS-158)**: recovery loop 付き rendering tool、 `generate_a2ui` 自動注入（Strands parity）、 intent="update" の surface 再構成、 google-adk floor 1.28.1 / `<3.0` 許可。 langgraph の progressive A2UI paint（inner `render_a2ui` デルタ stream、 native `OnChatModelStream` 経由）、 aws-strands の A2UI catalog parity + streamed catalogId stamp、 minimal ADK agent resolver 追加
0. **NEW: Knowledge Catalog 新規追跡開始** (`gcloud/knowledge-catalog`, 2026-06-14) - **Knowledge Catalog（旧 Dataplex）** の AI-powered data catalog 機能を示す samples / agents / tools リポを submodule 追加。 **Open Knowledge Format (OKF)** の metadata-as-code reference + **ADK ベース enrichment agent**（eval harness 同梱、 #42 / #28 / #40）が柱。 GenAI Toolbox の dataplex → knowledge-catalog リネーム (#3039) / DQ Scans 検索ツール (#2444) と同じ「Dataplex 改め Knowledge Catalog」軸の補完
0. **NEW: ADK Python v2.2.0** (2026-06-04) - Google GenAI SDK v2.0.0 対応、 AutoTracingPlugin（OTel 自動計装）、 RubricBasedMultiTurnTrajectoryEvaluator、 native `gen_ai.client.*` metrics、 A2A 連携強化（`to_a2a(Workflow)` / metadata 保持 / input-required vs auth-required）。 セキュリティ: Agent Builder path traversal / GCS skill Zip Slip / v0 actions unpickle 制限 / delete_session 所有権検証 / CVE-2026-48710（starlette・fastapi bump）。 LTS 側は v1.35.0 (2026-06-10) で Gemini 3.1 Live 修正を backport
0. **NEW: ADK JS v1.2.0** (2026-06-03) - v1.1.0 後のセキュリティ / 堅牢性修正を正式リリース。 後続 main で Skills Registry（Core + GCP remote + SearchSkillsTool、 #422-424）、 OpenAPI parser/auth handler part 2 (#385)、 streaming prototype pollution 修正 (#410)
0. **NEW: GenAI Toolbox v1.4.0** (2026-06-04) - Data Lineage 統合 (#3285)、 `--ignore-unknown-tools` (#3353)、 Cloud SQL PG vector assist tools (#3203)、 Spanner `search_catalog` (#3140)、 windows/arm64 配布。 セキュリティ: identifier injection 防止 (#3219)、 opaque token issuer 必須化 (#3360)、 Google/Generic OAuth 検証分離 (#3341)、 Looker filter escape (#3289)
0. **NEW: ADK Go v1.4.0** (2026-05-29) - Context unification（tool context を callbackContext にマージする内部統合: #871, #868）を軸に、 adka2a structured error propagation (#874)、 examples / CLI launcher の a2a-go/v2 SDK 移行 (#780)、 StreamingResponseAggregator の metadata-only SSE チャンク許容（abort せずストリーム継続: #918）、 conformance test recording plugin (#890) を取り込み
0. **NEW: GenAI Toolbox v1.3.0** (2026-05-21) - `cloud-sql-admin-execute-sql-many` / `cloud-sql-admin-sql-many` bulk ツール (#3083)、 SQLCommenter による client metadata 送出 (#3064)、 MCP auth tool-level scopes バリデーション (#3049)、 HTTP tool path traversal / base path scope escape 防止（セキュリティ: #3218）、 toolset/promptset boundary 強制 (#3036) を正式リリース。 後続の identifier injection 防止 (#3219) / thrift CVE-2026-41602 対応 (#3312) は v1.4.0 (2026-06-04) で正式リリース
0. **NEW: GKE MCP v0.13.0** (2026-05-28) - k8s リソース操作ツール群を一括拡充: `list_k8s_api_resources` (#378)、 `patch_k8s_resource` (#387)、 `get_k8s_rollout_status` (#386)、 `check_k8s_auth` (#385)、 `describe_k8s_resource` (#388)、 `get_k8s_cluster_info` (#379)、 `get_k8s_logs` (#370)、 `delete_k8s_resource` (#368)。 delete のデフォルト cascade policy を background 化 (#376)、 install checksum verification (#398)、 insecure `pull_request_target` 防止 CI (#400)
0. **NEW: Google Analytics MCP 0.6.0** (2026-05-21) - subprocess stdio handle inheritance 防止 (#154) を正式リリース。 v0.4.0 #151（tool call deadlock / stdout corruption）修正のフォローアップ deadlock を解消
0. **NEW: ADK Python v2.0.0 GA** (2026-05-19) - **Google ADK の v2.0 General Availability** 到達。 Multi-Agent Workflow Engine (Flexible Execution Graphs + Intelligent Task Delegation: 並列 sub-agent workers、 nested 階層チーム、 resilient dynamic scheduling) と Dynamic Agent Collaboration (Native Inter-Agent Routing: messaging / control state handoffs / context propagation) を production-grade に。 main ブランチを v2.0.0 へ transition。 アルファ (a1〜a3) / ベータ (b1) 経由でリリース
0. **NEW: ADK Go v1.3.0** (2026-05-20) - Live bidirectional streaming のコア機能を一括リリース: session resumption (#837)、 streaming tools (#836)、 audio cache for save artifact (#838)、 sequential agent live run (#835)、 live example (#834)、 core bidirectional streaming (#833)。 a2a-go/v2 対応、 VertexAI MemoryBank サポート、 user auth propagation 修正 (adka2a compat)
0. **NEW: Agent Starter Pack maintenance mode** (2026-05-21) - **公式に maintenance mode を surface**、 後継 **agents-cli** への移行を push (#967)。 Google の agent dev tooling 戦略は事実上 agents-cli へ移行
0. **NEW: UCP loyalty extension** (#340) - catalog / cart / checkout capability に loyalty 拡張を追加。 既存 discount 拡張に続く 2 つ目の正式拡張で、 commerce プロトコルの拡張軸が広がる
0. **NEW: UTCP v1.0** (直近 commit 2026-05-05, 新規追跡開始) - Universal Tool Calling Protocol。 MCP が proxy 経由ツール呼び出しなのに対し、 agent が discovery 後 native endpoint (HTTP/gRPC/WebSocket/CLI) を直接叩く設計で wrapper tax 削減。 v1.0 で plugin-based 構成へ再設計、 MCP プロトコル自体も plugin として包摂。 Python / TypeScript / Go 公式実装あり
0. **NEW: payments/ ディレクトリ新設** - 既存 commerce 系 5 件 (ACP / AP2 / UCP / x402 / Visa-TAP) を `protocols/` から `payments/` に分離 + Mastercard Verifiable Intent を新規追加で計 6 件。 generic protocols と決済系で関心領域を明確化
0. **NEW: Visa Trusted Agent Protocol** (新規追跡開始, `payments/`) - Agentic commerce における agent identity / authorization の cryptographic 標準。 AI エージェントが merchant に対して timestamp / session id / key id を含む暗号署名で identity と user 委任権限を証明。 既存 ACP/AP2/UCP/x402 の identity 補完レイヤ
0. **NEW: Mastercard Verifiable Intent v0.1.0** (2026-03-05 OSS化, 新規追跡開始, `payments/`) - Mastercard + Google 共同開発。 **SD-JWT (Selective Disclosure JWT)** ベースで user → agent への delegation scope を tamper-evident に証明。 Immediate / Autonomous の 2 実行モード。 FIDO/EMVCo/IETF/W3C ベース。 AP2 / UCP との相互運用設計。 Adyen / Worldpay / Fiserv / IBM / Checkout.com / Basis Theory / Getnet が支持表明
0. **NEW: NLIP 1st edition** (Ecma 承認 2025-12-10, 新規追跡開始) - Ecma TC56 が標準化した natural-language application-level プロトコル。 ECMA-430 本体 + 4 binding (HTTP/WebSocket/AMQP/Security profiles) + TR/113 解説書の 6 文書構成。 ISO 提出済み (2026-01-25)、 Claude Skills 互換 reference 実装は 2026-02-28 予定
0. **NEW: Gemini Cloud Assist MCP v0.8.0** (2026-04-21, 新規追跡開始) - GCP 環境を natural language で understand / manage / troubleshoot する MCP サーバー。 Local Node.js から Remote MCP Server architecture へ全面移行（**破壊的変更**）、 v0.2.0 (local) を完全 deprecate。 `designing-and-deploying-infrastructure` / `operating-google-cloud` skills 同梱。 現在 Private Preview (allowlist 制)
1. **ADK Python v1.33.0 → v1.34.0 → v2.0.0 GA** (2026-05-08 / 05-18 / 05-19) - 短期間で 3 リリース。 v1.33.0 で BufferableSessionService、 LlmResponse function call/response ヘルパー、 ApigeeLlm credential 注入、 adk web hot reload。 v1.34.0 で a2a persistent task stores、 Gemini Live API in ADK evaluate、 mTLS Cloud Telemetry exporter、 GCPSkillRegistry / Skill Registry 実装、 McpToolset OAuth PKCE。 v2.0.0 GA で multi-agent workflow engine と dynamic agent collaboration の production-grade 確立
1a. **ADK Python v1.31.x → v1.32.0** (2026-04-30) - **前安定リリース**。Anthropic thinking blocks、native OpenTelemetry agentic metrics、event compaction tracing、GcpAuthProvider 2LO/3LO/API Key sample、Cold start ~25% 短縮、複数のセキュリティ修正（SSRF/RCE/credential isolation/PubSub user_id sanitization）
2. **GKE MCP v0.11.1 → v0.12.0** - LLM 抽象 factory + Anthropic Claude ADK adapter、node pool 管理ツール、giq fetch_model_servers / fetch_profiles、GKE AI TPU トラブルシュート skill
3. **Google Analytics MCP v0.4.0 → 0.5.0** - 新規 conversions schema/spec ツール、 google-analytics-data v0.22.0 / admin v0.29.0 への依存バンプ。 v0.4.0 では `run_funnel_report` ツール（Data API v1alpha）、ADK 用 Skills、tool call deadlock / stdout corruption 修正
4. **MCP-UI v7.1.0 → v7.1.1** (2026-05-09) - sandbox proxy iframe timeout キャンセルで StrictMode unhandled rejection を防止。 v7.1.0 では AppRenderer に `hostInfo` / `hostCapabilities` props 追加 (2026-05-01)
5. **AP2 v0.1.0 → v0.2.0** (2026-04-28) - **V2 仕様正式リリース**。PaymentReceipt、X402 決済統合、Vertex AI 認証、Go サンプル、UCP 統合等を含む 7 ヶ月ぶりの大型リリース
6. **ADK JS v1.0.0 → v1.1.0 + 後続** - UrlContextTool（Gemini 2+ URL context）、Vertex AI Search Tool、MCP プレフィックス strip、AgentTool セッション再利用、Google Maps tool、VertexRagRetrievalTool、MCPToolset.getTools toolFilter
7. **ADK Go v1.2.0 → v1.3.0** (2026-05-20) - Live bidirectional streaming のコア (session resumption / streaming tools / audio cache / sequential agent live run / live example)、 a2a-go/v2 対応、 VertexAI MemoryBank、 stream_query simple text サポート、 `gen_ai.usage` 属性リネーム、 user auth propagation 修正
8. **ADK Python v1.30.0 → v1.31.1** - v1.31.x で Parameter Manager/Secret Manager ユーザーエージェント、Firestore、Vertex AI Agent Engine Sandbox、`memories.ingest_events`
9. **ACP v2026-01-30 → v2026-04-17 + 後続** - Cart Capability、Product Feeds API、Marketing Consent、Markdown Content Specification、Payment Intent、Mandatory Idempotency 等。リリース後も Order Schema Post-Checkout (#232)、`UpsertProductsResponse` JSON Schema 追加 (#241)、Meta TSC メンバー追加 (#236) など継続更新
10. **AG-UI release/2026-04-22** - State Snapshot/Delta コンパクション (#1535)、AgentCapabilities Python SDK 追加、Strands/Mastra アダプター修正、LFS マイグレーション
11. **MCP-Apps v1.7.0 → v1.7.1** - PDF Server lazy フォーム抽出 (#639)、キャッシュインスタンス間共有 (#637)、qr-server FastMCP host/port サポート (#372)
12. **OpenResponses + Phase Compaction** - WebSocket モード実装に加えて compact response エンドポイント、phase parameter 追加
13. **GenAI Toolbox v1.1.0 → v1.2.0** (2026-05-07) - **新たなマイナー安定リリース**。 Cloud Storage source (list/read + write/copy/move/delete)、 HTTPS/TLS listener、 BigQuery `maximumBytesBilled`、 Knowledge-catalog Data Quality Scans 検索ツールを正式取り込み。 v1.2.0 後では MCP auth tool-level scopes バリデーション (#3049)、 HTTP tool path traversal 防止 (#3218、 セキュリティ) 等が進行中
14. **MCP 2025-11-25 後** - **SEP-2567 (Sessionless MCP via Explicit State Handles) Final/Accepted 昇格** と **SEP-2575 (Make MCP Stateless)** によりステートレス志向への大型シフト進行中。 vm2 3.11.3 への GHSA-vwrp-x96c-mhwq 対応セキュリティバンプ。 MRTR (Multi-Round Tool Result) スキーマ整備、`InputRequiredResult` への rename、Augmented Tool Call フロー、SDK Working Group チャーター
15. **Agent Starter Pack v0.41.1 → v0.41.3 (+ maintenance mode)** - langgraph-prebuilt pin、 v0.41.2 で次世代プロジェクト「agents-cli」発表 (#952)、 v0.41.3 後の **#967 で公式に maintenance mode を surface し agents-cli へ移行を push**
16. **UCP v2026-04-08 以降** - **Identity Linking OAuth 2.0 foundation (#354, 破壊的)**、attribution フィールド (#391)、core-concepts 拡充 (#336)、Twum Djin Governance Council 追加
17. **gcloud-mcp storage-mcp-v0.5.1** - `delete_object` を destructive tools へ移動（セキュリティ強化）
18. **ADP データセット拡充** - per-step reward フィールド (#183)、CoderForge-Preview, Nemotron Terminal Corpus, Toucan, Toucan-1.5M, mini-coder トラジェクトリー、Catalog dataset ガイドライン (#186) など多数追加
19. **MCP Security secops-v0.7.0 後** - `list_parsers` ツール追加と return type 標準化 + pagination token 対応 (#252)
20. **Cloud Run MCP v1.10.0 後** - docker compose deployments、BUILD_ID base scheduled cloudbuild、Cloud Run skills

### 新規プロトコル統合

0. **UTCP (Universal Tool Calling Protocol)** - MCP の構造的代替案。 agent が proxy を介さず native endpoint を直接呼び出す。 既存 MCP は plugin として包摂され UTCP の中で共存可能
0. **Visa Trusted Agent Protocol** (`payments/`) - 大手金融プレイヤー (Visa) が回す agentic commerce identity 標準。 既存 ACP/AP2/UCP/x402 の identity 補完軸を埋める
0. **Mastercard Verifiable Intent** (`payments/`) - Mastercard + Google 共同。 SD-JWT chain で user → agent delegation scope を tamper-evident に verify。 Selective Disclosure でプライバシー保護寄り。 Visa TAP と並ぶ識別系の両極を成す
0. **NLIP (Natural Language Interaction Protocol)** - Ecma TC56 標準化、 ECMA-430〜434 + TR/113 構成。 既存ラインアップ（A2A: agent ↔ agent opaque / MCP: agent ↔ tool）と相補で natural-language application-level 通信を担当
0. **Gemini Cloud Assist MCP** - GCP 環境の natural-language operation 用 MCP サーバー（Private Preview）。 既存 cloud-run-mcp / gke-mcp / gcloud-mcp と並ぶ「GCP オペレーショナル」軸の補完
0. **Knowledge Catalog** (`gcloud/knowledge-catalog`) - Knowledge Catalog（旧 Dataplex）の data catalog / metadata 管理機能を示す samples + ADK enrichment agent。 OKF (Open Knowledge Format) で metadata-as-code を扱う。 GenAI Toolbox の knowledge-catalog ツール群と並ぶ「GCP データ context」軸の補完
1. **AP2 v0.2.0** - V2 仕様正式リリース。X402 決済、Vertex AI 認証、UCP 連携、Go サンプル
2. **ADK JS + UrlContextTool / Vertex AI Search Tool** - Gemini 2+ URL context grounding と Vertex AI Search ツール
3. **ADK Go + Agent Engine** - Agent Engine 統合、既存インスタンス更新、自動 session ID 生成
4. **ADK Python + Firestore / Vertex AI Agent Engine Sandbox** - Firestore サポートと Agent Engine Sandbox 統合
5. **ADK JS + Skills システム** - Skills interface、toolset、loader、script execution をサポート
6. **ADK JS + RoutedAgent/RoutedLlm** - 新しいルーティング型 Agent / LLM
7. **ADK Go + Skill Source proxy** - マージ/プリロード対応の skill source proxy 群
8. **GenAI Toolbox + Cloud Storage バケット/オブジェクト管理** - bucket/object 管理ツールと HTTPS/TLS リスナー
9. **ACP + Product Feeds / Cart Capability / Marketing Consent** - Commerce プロトコルの大幅拡張
9a. **UCP + Loyalty Extension** (#340) - catalog / cart / checkout capability に loyalty 拡張追加。 既存 discount 拡張に続く 2 つ目の正式拡張
9b. **GenAI Toolbox + cloud-sql-admin-execute-sql-many / sql-many** (#3083) - Cloud SQL admin 系の bulk execute/sql ツール
9c. **GKE MCP + apply_k8s_manifest + adk-anthropic-go** (#358, #356) - K8s manifest 適用ツール、 ADK 上の Anthropic Claude Go ライブラリ統合
9d. **ADK JS + Agent Engine Sandbox Code Executor** (#317) - Agent Engine Sandbox 経由のコード実行 Executor
9e. **ADK Python + GCPSkillRegistry / Skill Registry / Gemini Live API in evaluate** (v1.34.0) - Skill Registry 実装と Gemini Live API 評価対応
9f. **ADK Go + Live bidirectional streaming コア群** (v1.3.0) - session resumption / streaming tools / audio cache / sequential agent live run / live example
10. **A2UI + Kotlin SDK / C++ ポート** - Kotlin SDK conformance tests と Python エージェント SDK の C++ ポート初期実装
11. **ADP + per-step reward / 新規データセット群** - RL トレーニング用 reward フィールド、CoderForge-Preview/Nemotron Terminal Corpus/Toucan などのデータセット
12. **MCP-Apps + WebMCP-style ツール登録** - WebMCP 風のツール登録仕様
13. **OpenResponses + WebSocket / Phase Compaction** - WebSocket mode と compact response エンドポイント
14. **GKE MCP + GIQ tool** - GIQ tool を manifest agent に統合
15. **gcloud-mcp + backupdr-mcp** - Backup DR MCP サーバー新規追加
16. **AgentSkills + fast-agent / Google AI Edge Gallery / nanobot / Workshop.ai** - クライアントショーケース拡張
17. **A2A + カスタム protocol bindings** - カスタムプロトコルバインディングドキュメント追加

### セキュリティ更新

- **ADK Python (main, 2026-07-02〜07-07)**: **GcsArtifactService / InMemoryArtifactService のパスセグメント検証でクロスユーザー artifact アクセスを防止 (8718aeff)**、 **artifact 参照を呼び出し元スコープに制限 (f8631500)**、 **_OriginCheckMiddleware に DNS リバインディング保護を追加 (9a4f479d)**、 gepa サンプルの Jinja2 autoescape 有効化（XSS 対策、 a721c1eb）
- **ADK JS (main, 2026-07-01〜07-05)**: **`fetchOAuth2Tokens` の OAuth2 トークンエンドポイントに SSRF ブロックリストを適用 (#465)**
- **UCP (2026-07-02/03)**: **WBA 相互運用のため EdDSA (Ed25519, RFC 8037) 署名をオプション導入 (#483)**、 **名前空間権限バインディング規範化で名前空間なりすましを防止 (#530)**
- **GenAI Toolbox v1.6.0 (2026-06-30)**: **Kokoro code signing を release workflow に統合し Toolbox バイナリへ電子署名（サプライチェーン強化, #3528）**、 unsigned/signed GCS bucket 分離 + release table 生成時の署名検証、 長年の issue #996 対応
- **GKE MCP (2026-06-29)**: **UI 依存の脆弱性修正 (`ui/package-lock.json` 更新、 主に Babel toolchain 系 transitive 依存, #448)**
- **ADK Python (main, 2026-06-27)**: **AgentTool `config_path` 解決の path traversal 防止 (171ae9e)**、 **ContainerCodeExecutor sandbox のデフォルト hardening (0a9ce0f)**、 **YAML agent-config code reference の module blocklist (6a5be34)** / `adk web` 下での args denylist 強制 (e506fa6)
- **ADK JS v1.3.0 (2026-06-22)**: **streaming の prototype pollution 修正（model 制御 JSON path 経由, #410）**
- **MCP (2026-06-25)**: **Security best practices チュートリアル新設 (#1554)**、 **SECURITY.md に SDK 脆弱性開示プロセス + stdio trust-boundary ガイダンス追加 (#2973)**
- **ADK Python v2.3.0 (main, 2026-06-19)**: **Filename 経由の Code Generation Template Injection 修正**（ファイル名を介したテンプレートインジェクションを遮断）、 LiteLLM Claude thinking blocks の `display: "omitted"` 喪失修正
- **GenAI Toolbox v1.5.0 (2026-06-19)**: **`source/http` への SSRF guard 実装 (#3448)**、 **`source/cloudhealthcare` の pageURL 検証による SSRF 防止 (#3453)**、 **`bigquery-execute-sql` の dataset restriction bypass 阻止 (#3452)**、 **MCP auth と enable-api の同時有効化を fail させるガード (#3435)**、 InitializeConfigs での panic を error 返却化 (#3397)
- **ADK JS (main, 2026-06-18)**: **OAuth2 discovery の SSRF チェックで 127.0.0.0/8 と cloud-metadata ホスト名を遮断 (#431)**
- **A2UI (web_core, 2026-06-18)**: **`openUrl` を http/https プロトコルのみに制限 (#1707)**（不正スキーム遮断）
- **GenAI Toolbox (v1.4.0 後 main, 2026-06-18)**: **`mysql-get-query-plan` の query 実行バイパス + statement injection 防止 (#3235)**、 **cloud-storage source の bucket / local path アクセス制限 (#3454)**、 **auth/google で `mcpEnabled` 時に audience か clientId を必須化 (#3450)**、 JS doc サンプルの npm audit 脆弱性パッチ (#3442)
- **ADK Python (main, 2026-06-18)**: **code block 抽出での ReDoS 防止**、 **auth の missing client-credentials scopes の安全処理**、 生成 `.env` ファイルの operator safety 改善
- **GenAI Toolbox (v1.4.0 後 main, 2026-06-15)**: **picomatch を 2.3.2 / 4.0.4 に bump して regex method injection を解消 (#3426, #3429)**、 **fast-uri を 3.1.2 に bump して path normalization bypass を解消 (#3425)**
- **GenAI Toolbox (v1.4.0 後 main, 2026-06-12)**: **`applyEscape` の delimiter 文字 escape による SQL injection 防止 (#2811)**、 **MCP HTTP body size の上限設定 (#3216)**、 dataplex / datalineage の default credentials に cloud-platform scope 指定 (#3376)、 alloydb-omni prebuilt の password env 明示必須化 (#3398)
- **ADK Go (v1.4.0 後 main, 2026-06-10)**: **govulncheck advisory 対応で `golang.org/x/net` と otel OTLP exporters を patch 版へ bump (#994)**
- **ADK Python (main HEAD, 2026-06-13)**: CI セキュリティ硬化 — fork での workflow 実行を防ぐ repository check 追加、 pr-triage secrets を same-repository `pull_request_target` に gate、 release analyzer workflow input の shell 補間を停止
- **ADK Python v2.2.0 (2026-06-04)**: **Agent Builder file tools の path traversal ブロック (1fa7cda)**、 **GCS skill 展開の Zip Slip 修正 (2f15c6c)**、 **v0 actions blob の unpickle 制限 (9db48ce)**、 **`delete_session` の session 所有権検証 (b2916c7)**、 **CVE-2026-48710 対応（starlette / fastapi bump, 81add39）**、 ReadFileTool の shell escape (e16629b)、 OAuth2 token request の scope 省略 (6ce4b87)
- **ADK JS v1.2.0 (2026-06-03) + 後続 main**: v1.1.0 後の **CORS 脆弱性修正（express.urlencoded parser 無効化, #378）**、 **OAuth2 SSRF 防止（IPv4-mapped IPv6 ブロック, #354）**、 run_sse hardcoded `*` 削除 (#360)、 AdkApiServer host 制限 (#383) を正式リリース。 main では **streaming の prototype pollution 修正（model 制御 JSON path 経由, #410）**
- **GenAI Toolbox v1.4.0 (2026-06-04)**: **ClickHouse / BigQuery identifier injection 防止 (#3219)**、 **opaque token validation の issuer 必須化 (#3360)**、 **Google / Generic MCP OAuth 検証分離 (#3341)**、 Looker filter value escape (#3289)、 apache/thrift CVE-2026-41602 対応を正式リリース
- **MCP-Apps v1.7.4 (2026-06-04)**: **lazy-auth-server token exchange で PKCE 必須化 + redirect_uri バインド (#681)** — OAuth authorization code interception 攻撃を防止。 PKCE 非対応の旧フローは拒否される
- **GKE MCP v0.13.0 (2026-05-28)**: install 時の checksum verification 追加 (#398)、 insecure `pull_request_target` 利用を防ぐ CI チェック追加 (#400)
- **ADK Python v1.34.0 / v2.0.0 GA**: refreshed OAuth2 credentials の store 永続化 (218ea76, #5329)、 不要 OAuth フロー削除 (c35a579)、 Interactions API での dict 値 pre-serialization 起因の double-escape 防止 (85f397d)、 AnyIO CancelScope task boundary violations 防止 (4309159)、 AnthropicLlm import 時の OSError catch (91cb5c6)、 HITL イベントの誤 compaction 防止 (bb2efb6)
- **MCP HEAD (2025-11-25 後)**: **vm2 3.11.3 セキュリティバンプ GHSA-vwrp-x96c-mhwq** (#2711)
- **GenAI Toolbox (v1.3.0 後 → v1.4.0 で取り込み済み)**: **ClickHouse / BigQuery identifier injection 防止 (#3219)**、 **apache/thrift CVE-2026-41602 対応（v0.22.0 → v0.23.0, #3312）**、 Looker unquoted parameters の filter value escape (#3289)
- **GenAI Toolbox v1.3.0 (リリース済み, 2026-05-21)**: **HTTP tool path traversal / base path scope escape 防止 (#3218)**、 MCP auth tool-level scopes バリデーション (#3049)、 toolset/promptset boundary 強制 (#3036)
- **GenAI Toolbox v1.2.0 (リリース済み, 2026-05-07)**: SSE hardcoded `*` allowed origin 削除 (#3054、 セキュリティ取り込み)、 router-level logger injection (#3067)
- **ACP v2026-04-17 後 → UCP v2026-04-08 後**: urllib3 v2.7.0 セキュリティバンプ (#434)
- **ADK Python v1.33.0 後 HEAD**: AnthropicLlm import の OSError catch（クラッシュ回避）、 refreshed OAuth2 credentials の persist (auth) など safety hardening 多数
- **ADK Python v1.32.0 (リリース済み, 2026-04-30)**: **`load_web_page` SSRF / local-file アクセス修正 (0447e93)**、**nested YAML configs 経由の RCE 脆弱性ブロック (74f235b)**、credential isolation in auth context (race condition / データ漏洩防止) (5578772)、PubSub サブスクリプション / Eventarc source 由来 user_id サニタイズ (#5324, 0c4f157)、litellm 最低バージョンを 1.83.7 へ引き上げ CVE パッチ取り込み (6d2ada8)、Vertex RAG memory display name スコープ化 (784350d)
- **GenAI Toolbox (未リリースから v1.2.0 で取り込み済み)**: pgx v5.9.2 セキュリティ更新 (#3133)、SSE hardcoded `*` allowed origin 削除 (#3054)、macOS SDK を内部 GCS バケットに移行 (#3025)、pytest v9.0.3 セキュリティ更新 (#3047)
- **gcloud-mcp storage-mcp v0.6.0 (2026-05-06)**: `download_object_safe` ツール削除（破壊的変更、 destination パスへの sensitive 書き込みを許す設計だったため）。 destructive 経路の `download_object` または `read_object_content` / `read_object_metadata` への移行が必要 (#420, #422)
- **gcloud-mcp storage-mcp**: `delete_object` を safe → destructive tools へ移動（誤削除防止）
- **A2UI**: Python google-adk 1.28.1 へ bump（セキュリティ）
- **MCP-Apps v1.7.0**: vite / hono / @hono/node-server パッチバージョンへのバンプ (#616)
- **AG-UI**: CVE-2026-25528 依存関係脆弱性修正 (#1527)、ADK ミドルウェア critical/high Dependabot 脆弱性修正 (#1517)
- **ADK Python v1.30.0**: Agent Registry credential 漏洩脆弱性修正、path traversal バリデーション (#5110)
- **ADK JS**: FileArtifactService パストラバーサル脆弱性修正 (CWE-22)、lodash セキュリティ更新
- **UCP**: lodash セキュリティ更新（Trivy 脆弱性修正） (#333)、lockfile registries 標準化 (#368)
- **x402**: HTTPFacilitatorClient リダイレクト修正、Facilitator signer ランダム選択修正
- **MCP-Apps v1.4.0**: path-to-regexp ReDoS CVE 修正
- **GKE MCP v0.10.0**: Shell Command Injection 修正（`ui/scripts/build.ts`）
- **Google Analytics MCP**: google-adk 最低バージョン 1.28.1 更新（GHSA-rg7c-g689-fr3x 対応）
- **MCP**: OIDC / エンタープライズ管理認可更新、SEP-2207 リフレッシュトークンガイダンス
