import Glossary.Claim

/-!
# リポジトリ不変条件（旧 ADR 群のコード証明化）

`hironow/dotfiles` の現役アーキテクチャ決定（旧 ADR 0006, 0014, 0027, 0036, 0037,
0038, 0040, 0043, 0044, 0060, 0061, 0067, 0068, 0069, 0070, 0072, 0083, 0084, 0085, 0087）
を、人間向けの決定記録ではなく「コードアンカー＋Lean による機械検証済み主張」として定義する。
-/

namespace Glossary.Architecture

inductive Term where
  | misePinning
  | pythonToolchain
  | bunOnlyNode
  | podmanRuntime
  | telemetryLgtm
  | layeredClaudeSettings
  | selfSkillPrecedence
  | readonlyGitHooks
  | declaredRemoteMcp
  deriving DecidableEq, Repr

inductive Ctx where
  | toolchain
  | runtime
  | harness
  | governance
  deriving DecidableEq, Repr

open Term in
def terms : List (Entry Term Ctx) := [
  { id := misePinning, label := "mise 版ピン留めと単一生成元", context := .toolchain,
    gloss := "ホストのツール版は config/mise/config.toml、Dev Container と install.sh の凍結世代は config/mise/image-tools.toml（Go 生成器 tools/mise-versions/）を唯一の正本とする（旧 ADR 0006/0060/0061/0068）",
    anchors := [
      "config/mise/config.toml#[tools]",
      "config/mise/image-tools.toml#[bootstrap]"
    ] },
  { id := pythonToolchain, label := "Python 標準ツールチェーン（uv + ruff + ty）", context := .toolchain,
    gloss := "Python の依存管理・lint/format・型検査は uv / ruff / ty のみに統一し、mypy・pyright・pip 等は使わない（旧 ADR 0044/0069）",
    defDeps := [misePinning],
    anchors := [
      "config/mise/config.toml#uv = \"latest\"",
      "config/mise/config.toml#ruff = \"",
      "config/mise/config.toml#ty = \""
    ] },
  { id := bunOnlyNode, label := "Bun 専用 Node 方針と 7 日待機", context := .toolchain,
    gloss := "Node のパッケージ管理と mise の npm バックエンドは bun に統一し、npm_args ではなく bun_args を使う。JS 依存は bunfig.toml で 7 日間（604800 秒）待機する（旧 ADR 0027/0036/0040/0070/0079）",
    defDeps := [misePinning],
    anchors := [
      "config/mise/config.toml#bun = \"latest\"",
      "bunfig.toml#minimumReleaseAge = 604800"
    ] },
  { id := podmanRuntime, label := "Podman 5+ コンテナ標準", context := .runtime,
    gloss := "管理対象のコンテナ実行系は Podman 5 以上と podman-compose に統一し、Docker エンジンへ自動フォールバックしない（旧 ADR 0014/0067）",
    anchors := [
      "emulator/compose.yaml#services:"
    ] },
  { id := telemetryLgtm, label := "単一 otel-lgtm テレメトリ", context := .runtime,
    gloss := "ローカルテレメトリは上流の grafana/otel-lgtm コンテナ 1 つに統一し、独自設定やダッシュボードを持たない（旧 ADR 0072）",
    defDeps := [podmanRuntime],
    anchors := [
      "telemetry/compose.yaml#image: docker.io/grafana/otel-lgtm:"
    ] },
  { id := layeredClaudeSettings, label := "4 層 Claude 設定フラグメント", context := .harness,
    gloss := "Claude の settings.json は shared / OS / profile / machine-local の 4 層を順に合成して配布する（旧 ADR 0037）",
    anchors := [
      "scripts/sync_agents.py#SHARED_SETTINGS_FRAGMENT = \".claude/settings.shared.json\"",
      "scripts/sync_agents.py#OS_SETTINGS_OVERLAYS = ",
      "scripts/sync_agents.py#PROFILE_SETTINGS_DIR = \".claude/settings.profiles\"",
      "scripts/sync_agents.py#MACHINE_LOCAL_SETTINGS = \"settings.sync-local.json\""
    ] },
  { id := selfSkillPrecedence, label := "自作スキル優先則（hironow/skills）", context := .harness,
    gloss := "同名のスキルが存在するとき、hironow/skills 由来のスキルが第三者スキルに必ず優先し、restore_order でも最後に適用される（旧 ADR 0038/0043）",
    anchors := [
      "scripts/skills_lock.py#SELF_SOURCE = \"hironow/skills\"",
      "scripts/skills_lock.py#def _outranks(candidate: SkillRecord, existing: SkillRecord) -> bool:",
      "scripts/skills_lock.py#def restore_order(records: list[SkillRecord]) -> list[SkillRecord]:"
    ] },
  { id := readonlyGitHooks, label := "読み取り専用 Git フック（prek）", context := .governance,
    gloss := "Git フックは pre-commit と commit-msg の読み取り専用ガードのみに限り、ファイル書き換え・全リポジトリ検査・pre-push フックを持たない（旧 ADR 0083/0084/0085）",
    anchors := [
      ".pre-commit-config.yaml#default_install_hook_types: [pre-commit, commit-msg]",
      ".pre-commit-config.yaml#- id: forbidden-tokens-staged",
      ".pre-commit-config.yaml#- id: mise-versions-check"
    ] },
  { id := declaredRemoteMcp, label := "宣言済みリモート MCP 配布と秘密隔離", context := .harness,
    gloss := "秘密不要のリモート MCP サーバのみ dump/harness/mcp-servers.json から各エージェント CLI 経由で自動登録し、API キー等の秘密を要するサーバは guided のみで dotfiles を経由させない（旧 ADR 0087）",
    anchors := [
      "scripts/agent_mcp.py#DECLARATION = Path(__file__).resolve().parents[1] / \"dump/harness/mcp-servers.json\"",
      "scripts/agent_mcp.py#class Guided:",
      "dump/harness/mcp-servers.json#\"servers\":"
    ] }
]

theorem terms_wellFormed : WellFormed terms := check_sound _ (by decide)

-- ============================================================================
-- 機械検証済み不変条件（旧 ADR の規則を Lean の型・命題として転記・証明）
-- ============================================================================

/-- `scripts/skills_lock.py#_outranks` の規則の転記。 -/
structure SkillCandidate where
  isSelf : Bool
  resolvedByInstalled : Bool
  deriving DecidableEq, Repr

def outranks (candidate existing : SkillCandidate) : Bool :=
  if candidate.isSelf != existing.isSelf then
    candidate.isSelf
  else
    candidate.resolvedByInstalled && !existing.resolvedByInstalled

/-- `hironow/skills` 由来のスキルは、`resolvedBy` の違いによらず第三者スキルに必ず勝つ。 -/
theorem selfSource_outranks_thirdParty
    (c e : SkillCandidate) (hc : c.isSelf = true) (he : e.isSelf = false) :
    outranks c e = true ∧ outranks e c = false := by
  simp [outranks, hc, he]

/-- `.pre-commit-config.yaml` に登録されたフックの分類転記。 -/
inductive HookStage where
  | preCommit
  | commitMsg
  | prePush
  deriving DecidableEq, Repr

structure PrekHook where
  id : String
  stage : HookStage
  mutatesFiles : Bool
  deriving DecidableEq, Repr

def configuredPrekHooks : List PrekHook := [
  { id := "forbidden-tokens-staged", stage := .preCommit, mutatesFiles := false },
  { id := "forbidden-tokens-commit-msg", stage := .commitMsg, mutatesFiles := false },
  { id := "check-yaml", stage := .preCommit, mutatesFiles := false },
  { id := "check-toml", stage := .preCommit, mutatesFiles := false },
  { id := "check-json", stage := .preCommit, mutatesFiles := false },
  { id := "check-added-large-files", stage := .preCommit, mutatesFiles := false },
  { id := "check-merge-conflict", stage := .preCommit, mutatesFiles := false },
  { id := "detect-private-key", stage := .preCommit, mutatesFiles := false },
  { id := "mise-versions-check", stage := .preCommit, mutatesFiles := false }
]

def HookCompliant (h : PrekHook) : Bool :=
  !h.mutatesFiles && h.stage != .prePush

/-- 転記した `.pre-commit-config.yaml` の全フックは読み取り専用であり、pre-push を含まない。 -/
theorem prek_hooks_readonly_no_prepush :
    configuredPrekHooks.all HookCompliant = true := by
  decide

/-- `scripts/agent_mcp.py` のサーバ登録分類（自動登録 vs guided 手動案内）の転記。 -/
inductive McpRoute where
  | autoRegister
  | guidedOnly
  deriving DecidableEq, Repr

def routeMcpServer (needsSecret : Bool) : McpRoute :=
  if needsSecret then .guidedOnly else .autoRegister

/-- 秘密を要する MCP サーバは、いかなる場合も自動登録へ振り分けられない。 -/
theorem mcp_secret_never_auto_registered (needsSecret : Bool) (h : needsSecret = true) :
    routeMcpServer needsSecret ≠ .autoRegister := by
  rw [h]
  decide

open Term in
def claims : List (Claim Term) := [
  { about := [misePinning, pythonToolchain, bunOnlyNode, podmanRuntime, readonlyGitHooks],
    statement := "リポジトリ不変条件の用語集は ID が一意で、参照先が存在し、定義が循環していない",
    verdict := .proved,
    evidence := .lean "Glossary.Architecture.terms_wellFormed" (WellFormed terms) terms_wellFormed },
  { about := [selfSkillPrecedence],
    statement := "scripts/skills_lock.py#_outranks の規則の転記において、hironow/skills 由来のスキルは resolvedBy によらず第三者スキルに必ず優先し、逆転しない",
    verdict := .proved,
    evidence := .lean "Glossary.Architecture.selfSource_outranks_thirdParty"
      (∀ c e : SkillCandidate, c.isSelf = true → e.isSelf = false →
        outranks c e = true ∧ outranks e c = false)
      selfSource_outranks_thirdParty },
  { about := [readonlyGitHooks],
    statement := ".pre-commit-config.yaml のフック一覧の転記において、登録された 9 個のフックはすべて読み取り専用であり pre-push ステージを含まない",
    verdict := .proved,
    evidence := .lean "Glossary.Architecture.prek_hooks_readonly_no_prepush"
      (configuredPrekHooks.all HookCompliant = true)
      prek_hooks_readonly_no_prepush },
  { about := [declaredRemoteMcp],
    statement := "scripts/agent_mcp.py の振り分け規則の転記において、秘密を要する MCP サーバは自動登録（autoRegister）されない",
    verdict := .proved,
    evidence := .lean "Glossary.Architecture.mcp_secret_never_auto_registered"
      (∀ needsSecret : Bool, needsSecret = true → routeMcpServer needsSecret ≠ .autoRegister)
      mcp_secret_never_auto_registered },
  { about := [readonlyGitHooks, declaredRemoteMcp],
    statement := "既存の Proposed 状態 ADR（0065 kernel-cve evidence-only、0085、0087）および退役済み Coder 関連 ADR（0002〜0013, 0045）は、docs/adr/ 削除後に git 履歴のみへ委ねてよいか？",
    verdict := .undecided,
    evidence := .questionOutsideModel "過去の経緯や未決裁 ADR を git 履歴のみに残すか否かは運用上の意思決定であり、状態機械モデルでは決定できない" }
]

def book : Book Term Ctx :=
  { title := "リポジトリ不変条件（旧ADR群の証明化）",
    terms,
    claims,
    stopScene := .inBook "配布・同期・スキル配置" }

theorem book_check : book.check = true := by decide

end Glossary.Architecture
