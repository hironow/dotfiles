<!-- 生成物。`just generate` が `Glossary/*.lean` から作る。手で編集しない。 -->

# 実装との対応

各用語が実装のどこに当たるか。対応が切れると `just check` が落ちる。

## 配布・同期・スキル配置

| 用語 | ID | ファイル | そこにあるべき文字列 |
|---|---|---|---|
| 指示・設定の正本 | `canonicalSource` | `scripts/sync_agents.py` | `BASE_FILE = "ROOT_AGENTS.md"` |
| 指示・設定の正本 | `canonicalSource` | `scripts/sync_agents.py` | `OVERLAY_FILE = "ROOT_CLAUDE.md"` |
| 指示・設定の正本 | `canonicalSource` | `scripts/sync_agents.py` | `HOOK_SETTINGS_FRAGMENT = ".claude/settings.hooks.json"` |
| エージェントホーム | `agentHome` | `scripts/sync_agents.py` | `AGENTS: list[AgentTarget] = [` |
| エージェントホーム | `agentHome` | `scripts/skills_lock.py` | `CONSUMER_HOMES = (` |
| 切替ロックとジャーナル | `switchLock` | `scripts/agent_hook_wiring.py` | `def journal(self, key: str) -> Path:` |
| 切替ロックとジャーナル | `switchLock` | `scripts/agent_hook_wiring.py` | `def lock(self) -> Path:` |
| 同期マニフェスト | `syncManifest` | `scripts/sync_agents.py` | `SYNC_DIRECTORIES = ["commands", "agents"]` |
| 同期マニフェスト | `syncManifest` | `scripts/sync_agents.py` | `def _save_manifest(` |
| 外部スキルストア反映 | `storeInstall` | `scripts/skills_lock.py` | `SKILLS_CLI_VERSION = "1.5.22"` |
| 外部スキルストア反映 | `storeInstall` | `scripts/skills_lock.py` | `def build_restore_command(record: SkillRecord)` |
| 配置済みスキル | `placedSkill` | `scripts/skills_lock.py` | `STATE_FILE = ".skills-lock-state.json"` |
| 配置済みスキル | `placedSkill` | `scripts/skills_lock.py` | `tmp.replace(state_file)` |
| 配置済みスキル | `placedSkill` | `scripts/skills_lock.py` | `def _swap_in(` |
| 配置済みスキル | `placedSkill` | `scripts/skills_lock.py` | `def place(` |
| 登録済みフック | `wiredHook` | `scripts/agent_hook_sync.py` | `def apply_home(self, key: str) -> HomeResult:` |
| 登録済みフック | `wiredHook` | `scripts/sync_agents.py` | `result = hook_session.apply_home(plan.agent.key)` |
| 配布・同期の中断 | `syncStop` | `scripts/sync_agents.py` | `raise hook_sync.SyncStopped(` |
| 配布・同期の中断 | `syncStop` | `scripts/agent_hook_sync.py` | `raise wiring.ChangedSinceRead(` |
| プレビュー実行 | `previewMode` | `scripts/sync_agents.py` | `def preview_mode(` |
| 診断と手動復旧 | `doctorRecovery` | `scripts/deploy.sh` | `run_agent_steps()` |
| 診断と手動復旧 | `doctorRecovery` | `scripts/doctor.sh` | `doctor` |

## リポジトリ不変条件（旧ADR群の証明化）

| 用語 | ID | ファイル | そこにあるべき文字列 |
|---|---|---|---|
| mise 版ピン留めと単一生成元 | `misePinning` | `config/mise/config.toml` | `[tools]` |
| mise 版ピン留めと単一生成元 | `misePinning` | `config/mise/image-tools.toml` | `[bootstrap]` |
| Python 標準ツールチェーン（uv + ruff + ty） | `pythonToolchain` | `config/mise/config.toml` | `uv = "latest"` |
| Python 標準ツールチェーン（uv + ruff + ty） | `pythonToolchain` | `config/mise/config.toml` | `ruff = "` |
| Python 標準ツールチェーン（uv + ruff + ty） | `pythonToolchain` | `config/mise/config.toml` | `ty = "` |
| Bun 専用 Node 方針と 7 日待機 | `bunOnlyNode` | `config/mise/config.toml` | `bun = "latest"` |
| Bun 専用 Node 方針と 7 日待機 | `bunOnlyNode` | `bunfig.toml` | `minimumReleaseAge = 604800` |
| Podman 5+ コンテナ標準 | `podmanRuntime` | `emulator/compose.yaml` | `services:` |
| 単一 otel-lgtm テレメトリ | `telemetryLgtm` | `telemetry/compose.yaml` | `image: docker.io/grafana/otel-lgtm:` |
| 4 層 Claude 設定フラグメント | `layeredClaudeSettings` | `scripts/sync_agents.py` | `SHARED_SETTINGS_FRAGMENT = ".claude/settings.shared.json"` |
| 4 層 Claude 設定フラグメント | `layeredClaudeSettings` | `scripts/sync_agents.py` | `OS_SETTINGS_OVERLAYS = ` |
| 4 層 Claude 設定フラグメント | `layeredClaudeSettings` | `scripts/sync_agents.py` | `PROFILE_SETTINGS_DIR = ".claude/settings.profiles"` |
| 4 層 Claude 設定フラグメント | `layeredClaudeSettings` | `scripts/sync_agents.py` | `MACHINE_LOCAL_SETTINGS = "settings.sync-local.json"` |
| 自作スキル優先則（hironow/skills） | `selfSkillPrecedence` | `scripts/skills_lock.py` | `SELF_SOURCE = "hironow/skills"` |
| 自作スキル優先則（hironow/skills） | `selfSkillPrecedence` | `scripts/skills_lock.py` | `def _outranks(candidate: SkillRecord, existing: SkillRecord) -> bool:` |
| 自作スキル優先則（hironow/skills） | `selfSkillPrecedence` | `scripts/skills_lock.py` | `def restore_order(records: list[SkillRecord]) -> list[SkillRecord]:` |
| 読み取り専用 Git フック（prek） | `readonlyGitHooks` | `.pre-commit-config.yaml` | `default_install_hook_types: [pre-commit, commit-msg]` |
| 読み取り専用 Git フック（prek） | `readonlyGitHooks` | `.pre-commit-config.yaml` | `- id: forbidden-tokens-staged` |
| 読み取り専用 Git フック（prek） | `readonlyGitHooks` | `.pre-commit-config.yaml` | `- id: mise-versions-check` |
| 宣言済みリモート MCP 配布と秘密隔離 | `declaredRemoteMcp` | `scripts/agent_mcp.py` | `DECLARATION = Path(__file__).resolve().parents[1] / "dump/harness/mcp-servers.json"` |
| 宣言済みリモート MCP 配布と秘密隔離 | `declaredRemoteMcp` | `scripts/agent_mcp.py` | `class Guided:` |
| 宣言済みリモート MCP 配布と秘密隔離 | `declaredRemoteMcp` | `dump/harness/mcp-servers.json` | `"servers":` |

