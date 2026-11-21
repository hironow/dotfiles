import Glossary.Claim

/-!
# 配布・同期・スキル配置（Deploy / Sync / Skills）

`scripts/deploy.sh`、`scripts/sync_agents.py`、`scripts/agent_hook_sync.py`、
`scripts/agent_hook_wiring.py`、`scripts/skills_lock.py` を正本コードとする用語集と主張。
配布・同期の途中中断（`SyncStopped` / プロセス終了）と仕掛り状態（未永続化の配置状態・
外部ストア更新・ホーム別フック登録）の競合を Quint モデルで検証する。
-/

namespace Glossary.DeploySync

inductive Term where
  | canonicalSource
  | agentHome
  | switchLock
  | syncManifest
  | storeInstall
  | placedSkill
  | wiredHook
  | syncStop
  | previewMode
  | doctorRecovery
  deriving DecidableEq, Repr

inductive Ctx where
  | source
  | distribution
  | skills
  | operations
  deriving DecidableEq, Repr

open Term

def terms : List (Entry Term Ctx) := [
  { id := canonicalSource, label := "指示・設定の正本", context := .source,
    gloss := "リポジトリルートに置く ROOT_AGENTS.md / ROOT_CLAUDE.md / .claude/settings.*.json 群。配布元であり、ホーム側の直接編集は次回同期で上書きされる",
    anchors := [
      "scripts/sync_agents.py#BASE_FILE = \"ROOT_AGENTS.md\"",
      "scripts/sync_agents.py#OVERLAY_FILE = \"ROOT_CLAUDE.md\"",
      "scripts/sync_agents.py#HOOK_SETTINGS_FRAGMENT = \".claude/settings.hooks.json\""
    ] },
  { id := agentHome, label := "エージェントホーム", role := some .resource, context := .distribution,
    gloss := "各エージェントが設定・指示・スキルを読むホームディレクトリ（~/.claude, ~/.claude-work-{a..d}, ~/.codex, ~/.gemini）",
    anchors := [
      "scripts/sync_agents.py#AGENTS: list[AgentTarget] = [",
      "scripts/skills_lock.py#CONSUMER_HOMES = ("
    ] },
  { id := switchLock, label := "切替ロックとジャーナル", role := some .hold, context := .distribution,
    gloss := "ホーム単位のフック切替中に排他と復旧証跡を保持する switch.lock および switch-<home>.json",
    defDeps := [agentHome],
    anchors := [
      "scripts/agent_hook_wiring.py#def journal(self, key: str) -> Path:",
      "scripts/agent_hook_wiring.py#def lock(self) -> Path:"
    ] },
  { id := syncManifest, label := "同期マニフェスト", context := .distribution,
    gloss := "dotfiles 側で追跡するディレクトリ項目（commands, agents）を記録する .sync-manifest.json。同期末尾で保存される",
    defDeps := [canonicalSource, agentHome],
    anchors := [
      "scripts/sync_agents.py#SYNC_DIRECTORIES = [\"commands\", \"agents\"]",
      "scripts/sync_agents.py#def _save_manifest("
    ] },
  { id := storeInstall, label := "外部スキルストア反映", role := some .externalConfirmation, context := .skills,
    gloss := "ピン留めした外部 CLI（bunx skills@1.5.22）による ~/.agents/skills と .skill-lock.json への書き込み。同期処理の外部で上流世代が更新され得る",
    anchors := [
      "scripts/skills_lock.py#SKILLS_CLI_VERSION = \"1.5.22\"",
      "scripts/skills_lock.py#def build_restore_command(record: SkillRecord)"
    ] },
  { id := placedSkill, label := "配置済みスキル", role := some .entitlement, context := .skills,
    gloss := "各エージェントホームの skills/ へ相対シンボリックリンク（不可時はコピー＋.skills-lock-state.json 記録）として配置されたスキル",
    defDeps := [agentHome, storeInstall],
    anchors := [
      "scripts/skills_lock.py#STATE_FILE = \".skills-lock-state.json\"",
      "scripts/skills_lock.py#def _swap_in(",
      "scripts/skills_lock.py#def place("
    ] },
  { id := wiredHook, label := "登録済みフック", role := some .entitlement, context := .distribution,
    gloss := "agent-hook バイナリまたは設定フラグメントがホームの settings.json / hooks.json に確定登録された状態",
    defDeps := [canonicalSource, agentHome, switchLock],
    anchors := [
      "scripts/agent_hook_sync.py#def apply_home(self, key: str) -> HomeResult:"
    ] },
  { id := syncStop, label := "配布・同期の中断", role := some .stop, context := .operations,
    gloss := "apply_home の停止（SyncStopped / ChangedSinceRead）やプロセス途中終了により、配布・配置ループが完走前に止まること",
    defDeps := [switchLock, placedSkill, wiredHook],
    anchors := [
      "scripts/sync_agents.py#raise hook_sync.SyncStopped(",
      "scripts/agent_hook_sync.py#raise wiring.ChangedSinceRead("
    ] },
  { id := previewMode, label := "プレビュー実行", role := some .plannedStop, context := .operations,
    gloss := "ホームへ一切書き込まずに差分計画のみを表示する --preview 実行（just sync-agents-preview）",
    defDeps := [canonicalSource, agentHome],
    anchors := [
      "scripts/sync_agents.py#def preview_mode("
    ] },
  { id := doctorRecovery, label := "診断と手動復旧", role := some .fallbackChannel, context := .operations,
    gloss := "中断・ドリフト発生後に just doctor で状態を診断し、just sync-agents / just skills-place / 個別レシピで再同期する経路",
    defDeps := [agentHome, syncStop],
    anchors := [
      "scripts/deploy.sh#run_agent_steps()",
      "scripts/doctor.sh#doctor"
    ] }
]

theorem terms_wellFormed : WellFormed terms := check_sound _ (by decide)

def deploySpec (main invariant : String) : QuintRef :=
  { file := "Spec/deploy_sync.qnt", main, invariant }

def claims : List (Claim Term) := [
  { about := [canonicalSource, agentHome, switchLock, placedSkill, wiredHook],
    statement := "配布・同期用語集は ID が一意で、参照先が存在し、定義が循環していない",
    verdict := .proved,
    evidence := .lean "Glossary.DeploySync.terms_wellFormed" (WellFormed terms) terms_wellFormed },
  { about := [placedSkill, storeInstall, syncStop],
    statement := "現行コードそのまま（scripts/skills_lock.py#place のループ末尾一括 _save_state）では、コピー配置途中で中断して外部ストアが更新されても、dotfiles が配置したコピーが未記録の孤児（kept）にならない",
    verdict := .counterexample,
    evidence := .violated (deploySpec "codeAsIs" "noOrphanedCopy") },
  { about := [wiredHook, agentHome, syncStop],
    statement := "現行コードそのまま（scripts/sync_agents.py#sync_mode のファイル先行書き込み）では、apply_home が中断してもホーム内の指示ファイル世代とフック登録世代が分裂しない",
    verdict := .counterexample,
    evidence := .violated (deploySpec "codeAsIs" "noSplitHome") },
  { about := [placedSkill, storeInstall, syncStop],
    statement := "提案設計（_swap_in ごとに .skills-lock-state.json を永続化）では、配布中断と外部ストア更新を経ても未記録の孤児コピー（kept）が生じない",
    verdict := .proved,
    evidence := .holds (deploySpec "guarded" "noOrphanedCopy") },
  { about := [wiredHook, agentHome, syncStop],
    statement := "提案設計（ホーム単位でフック登録と指示ファイル更新を揃えて確定）では、配布中断が起きても単一ホーム内で指示とフックの世代が分裂しない",
    verdict := .proved,
    evidence := .holds (deploySpec "guarded" "noSplitHome") },
  { about := [agentHome, wiredHook, syncStop],
    statement := "提案設計（ホーム単位の原子的確定）であっても、複数ホーム同期の途中で中断したとき全ホームの世代が常に一致する",
    verdict := .counterexample,
    evidence := .violated (deploySpec "guarded" "allHomesConsistent") },
  { about := [placedSkill, syncStop, doctorRecovery],
    statement := "skills_lock.py のコピーモード配置で途中中断した場合、_save_state を項目ごとに永続化すべきか、それとも --force による手動復旧に委ねるか？",
    verdict := .undecided,
    evidence := .question [deploySpec "codeAsIs" "noOrphanedCopy"] },
  { about := [wiredHook, agentHome, syncStop],
    statement := "sync_agents.py で hook_session.apply_home が停止したとき、直前に書き込んだ指示ファイル（CLAUDE.md / AGENTS.md）をロールバックすべきか？",
    verdict := .undecided,
    evidence := .question [deploySpec "codeAsIs" "noSplitHome"] },
  { about := [agentHome, wiredHook, syncStop],
    statement := "複数ホーム同期で一部ホームだけ apply_home が停止したとき、完了済みホームを新世代のまま進める（現行の継続方針）か、全ホームを旧世代へ戻すべきか？",
    verdict := .undecided,
    evidence := .question [deploySpec "guarded" "allHomesConsistent"] }
]

def book : Book Term Ctx :=
  { title := "配布・同期・スキル配置", terms, claims, stopScene := .modelled }

theorem book_check : book.check = true := by decide

end Glossary.DeploySync
