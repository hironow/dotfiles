<!-- 生成物。`just generate` が `Glossary/*.lean` から作る。手で編集しない。 -->

# 用語と主張

## 配布・同期・スキル配置

### 用語

| 用語 | ID | 文脈 | 定義 | 定義依存 | 関連 |
|---|---|---|---|---|---|
| 指示・設定の正本 | `canonicalSource` | source | リポジトリルートに置く ROOT_AGENTS.md / ROOT_CLAUDE.md / .claude/settings.*.json 群。配布元であり、ホーム側の直接編集は次回同期で上書きされる |  |  |
| エージェントホーム | `agentHome` | distribution | 各エージェントが設定・指示・スキルを読むホームディレクトリ（~/.claude, ~/.claude-work-{a..d}, ~/.codex, ~/.gemini） |  |  |
| 切替ロックとジャーナル | `switchLock` | distribution | ホーム単位のフック切替中に排他と復旧証跡を保持する switch.lock および switch-<home>.json | エージェントホーム |  |
| 同期マニフェスト | `syncManifest` | distribution | dotfiles 側で追跡するディレクトリ項目（commands, agents）を記録する .sync-manifest.json。同期末尾で保存される | 指示・設定の正本, エージェントホーム |  |
| 外部スキルストア反映 | `storeInstall` | skills | ピン留めした外部 CLI（bunx skills@1.5.22）による ~/.agents/skills と .skill-lock.json への書き込み。同期処理の外部で上流世代が更新され得る |  |  |
| 配置済みスキル | `placedSkill` | skills | 各エージェントホームの skills/ へ相対シンボリックリンク（不可時はコピー＋.skills-lock-state.json 記録）として配置されたスキル | エージェントホーム, 外部スキルストア反映 |  |
| 登録済みフック | `wiredHook` | distribution | agent-hook バイナリまたは設定フラグメントがホームの settings.json / hooks.json に確定登録された状態 | 指示・設定の正本, エージェントホーム, 切替ロックとジャーナル |  |
| 配布・同期の中断 | `syncStop` | operations | apply_home の停止（SyncStopped / ChangedSinceRead）やプロセス途中終了により、配布・配置ループが完走前に止まること | 切替ロックとジャーナル, 配置済みスキル, 登録済みフック |  |
| プレビュー実行 | `previewMode` | operations | ホームへ一切書き込まずに差分計画のみを表示する --preview 実行（just sync-agents-preview） | 指示・設定の正本, エージェントホーム |  |
| 診断と手動復旧 | `doctorRecovery` | operations | 中断・ドリフト発生後に just doctor で状態を診断し、just sync-agents / just skills-place / 個別レシピで再同期する経路 | エージェントホーム, 配布・同期の中断 |  |

### 主張

| 判定 | 主張 | 用語 | 証拠 |
|---|---|---|---|
| 証明済み | 配布・同期用語集は ID が一意で、参照先が存在し、定義が循環していない | 指示・設定の正本, エージェントホーム, 切替ロックとジャーナル, 配置済みスキル, 登録済みフック | Lean: `Glossary.DeploySync.terms_wellFormed` |
| 反例あり | 現行コードそのまま（scripts/skills_lock.py#place のループ末尾一括 _save_state）では、コピー配置途中で中断して外部ストアが更新されても、dotfiles が配置したコピーが未記録の孤児（kept）にならない | 配置済みスキル, 外部スキルストア反映, 配布・同期の中断 | Quint 反例: `Spec/deploy_sync.qnt` `codeAsIs.noOrphanedCopy` |
| 反例あり | 現行コードそのまま（scripts/sync_agents.py#sync_mode のファイル先行書き込み）では、apply_home が中断してもホーム内の指示ファイル世代とフック登録世代が分裂しない | 登録済みフック, エージェントホーム, 配布・同期の中断 | Quint 反例: `Spec/deploy_sync.qnt` `codeAsIs.noSplitHome` |
| 証明済み | 提案設計（_swap_in ごとに .skills-lock-state.json を永続化）では、配布中断と外部ストア更新を経ても未記録の孤児コピー（kept）が生じない | 配置済みスキル, 外部スキルストア反映, 配布・同期の中断 | Quint + TLC 全状態: `Spec/deploy_sync.qnt` `guarded.noOrphanedCopy` |
| 証明済み | 提案設計（ホーム単位でフック登録と指示ファイル更新を揃えて確定）では、配布中断が起きても単一ホーム内で指示とフックの世代が分裂しない | 登録済みフック, エージェントホーム, 配布・同期の中断 | Quint + TLC 全状態: `Spec/deploy_sync.qnt` `guarded.noSplitHome` |
| 反例あり | 提案設計（ホーム単位の原子的確定）であっても、複数ホーム同期の途中で中断したとき全ホームの世代が常に一致する | エージェントホーム, 登録済みフック, 配布・同期の中断 | Quint 反例: `Spec/deploy_sync.qnt` `guarded.allHomesConsistent` |
| 未決定 | skills_lock.py のコピーモード配置で途中中断した場合、_save_state を項目ごとに永続化すべきか、それとも --force による手動復旧に委ねるか？ | 配置済みスキル, 配布・同期の中断, 診断と手動復旧 | 業務側への質問。空白を示す反例: `Spec/deploy_sync.qnt` `codeAsIs.noOrphanedCopy` |
| 未決定 | sync_agents.py で hook_session.apply_home が停止したとき、直前に書き込んだ指示ファイル（CLAUDE.md / AGENTS.md）をロールバックすべきか？ | 登録済みフック, エージェントホーム, 配布・同期の中断 | 業務側への質問。空白を示す反例: `Spec/deploy_sync.qnt` `codeAsIs.noSplitHome` |
| 未決定 | 複数ホーム同期で一部ホームだけ apply_home が停止したとき、完了済みホームを新世代のまま進める（現行の継続方針）か、全ホームを旧世代へ戻すべきか？ | エージェントホーム, 登録済みフック, 配布・同期の中断 | 業務側への質問。空白を示す反例: `Spec/deploy_sync.qnt` `guarded.allHomesConsistent` |

## リポジトリ不変条件（旧ADR群の証明化）

### 用語

| 用語 | ID | 文脈 | 定義 | 定義依存 | 関連 |
|---|---|---|---|---|---|
| mise 版ピン留めと単一生成元 | `misePinning` | toolchain | ホストのツール版は config/mise/config.toml、Dev Container と install.sh の凍結世代は config/mise/image-tools.toml（Go 生成器 tools/mise-versions/）を唯一の正本とする（旧 ADR 0006/0060/0061/0068） |  |  |
| Python 標準ツールチェーン（uv + ruff + ty） | `pythonToolchain` | toolchain | Python の依存管理・lint/format・型検査は uv / ruff / ty のみに統一し、mypy・pyright・pip 等は使わない（旧 ADR 0044/0069） | mise 版ピン留めと単一生成元 |  |
| Bun 専用 Node 方針と 7 日待機 | `bunOnlyNode` | toolchain | Node のパッケージ管理と mise の npm バックエンドは bun に統一し、npm_args ではなく bun_args を使う。JS 依存は bunfig.toml で 7 日間（604800 秒）待機する（旧 ADR 0027/0036/0040/0070/0079） | mise 版ピン留めと単一生成元 |  |
| Podman 5+ コンテナ標準 | `podmanRuntime` | runtime | 管理対象のコンテナ実行系は Podman 5 以上と podman-compose に統一し、Docker エンジンへ自動フォールバックしない（旧 ADR 0014/0067） |  |  |
| 単一 otel-lgtm テレメトリ | `telemetryLgtm` | runtime | ローカルテレメトリは上流の grafana/otel-lgtm コンテナ 1 つに統一し、独自設定やダッシュボードを持たない（旧 ADR 0072） | Podman 5+ コンテナ標準 |  |
| 4 層 Claude 設定フラグメント | `layeredClaudeSettings` | harness | Claude の settings.json は shared / OS / profile / machine-local の 4 層を順に合成して配布する（旧 ADR 0037） |  |  |
| 自作スキル優先則（hironow/skills） | `selfSkillPrecedence` | harness | 同名のスキルが存在するとき、hironow/skills 由来のスキルが第三者スキルに必ず優先し、restore_order でも最後に適用される（旧 ADR 0038/0043） |  |  |
| 読み取り専用 Git フック（prek） | `readonlyGitHooks` | governance | Git フックは pre-commit と commit-msg の読み取り専用ガードのみに限り、ファイル書き換え・全リポジトリ検査・pre-push フックを持たない（旧 ADR 0083/0084/0085） |  |  |
| 宣言済みリモート MCP 配布と秘密隔離 | `declaredRemoteMcp` | harness | 秘密不要のリモート MCP サーバのみ dump/harness/mcp-servers.json から各エージェント CLI 経由で自動登録し、API キー等の秘密を要するサーバは guided のみで dotfiles を経由させない（旧 ADR 0087） |  |  |

### 主張

| 判定 | 主張 | 用語 | 証拠 |
|---|---|---|---|
| 証明済み | リポジトリ不変条件の用語集は ID が一意で、参照先が存在し、定義が循環していない | mise 版ピン留めと単一生成元, Python 標準ツールチェーン（uv + ruff + ty）, Bun 専用 Node 方針と 7 日待機, Podman 5+ コンテナ標準, 読み取り専用 Git フック（prek） | Lean: `Glossary.Architecture.terms_wellFormed` |
| 証明済み | scripts/skills_lock.py#_outranks の規則の転記において、hironow/skills 由来のスキルは resolvedBy によらず第三者スキルに必ず優先し、逆転しない | 自作スキル優先則（hironow/skills） | Lean: `Glossary.Architecture.selfSource_outranks_thirdParty` |
| 証明済み | .pre-commit-config.yaml のフック一覧の転記において、登録された 9 個のフックはすべて読み取り専用であり pre-push ステージを含まない | 読み取り専用 Git フック（prek） | Lean: `Glossary.Architecture.prek_hooks_readonly_no_prepush` |
| 証明済み | scripts/agent_mcp.py の振り分け規則の転記において、秘密を要する MCP サーバは自動登録（autoRegister）されない | 宣言済みリモート MCP 配布と秘密隔離 | Lean: `Glossary.Architecture.mcp_secret_never_auto_registered` |
| 未決定 | 既存の Proposed 状態 ADR（0065 kernel-cve evidence-only、0085、0087）および退役済み Coder 関連 ADR（0002〜0013, 0045）は、docs/adr/ 削除後に git 履歴のみへ委ねてよいか？ | 読み取り専用 Git フック（prek）, 宣言済みリモート MCP 配布と秘密隔離 | 業務側への質問。モデルで示せない理由: 過去の経緯や未決裁 ADR を git 履歴のみに残すか否かは運用上の意思決定であり、状態機械モデルでは決定できない |

