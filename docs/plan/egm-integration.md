# EGM integration

State: done (current usage: [EGM runbook](../runbook/egm.md)).
The owner has been notified and authorized commits and PR publication from
`feat/egm-integration`, followed by squash merge only after all applicable CI
passes on the exact PR head. Commit the clipboard fixture fix first (structural),
then the EGM feature. Live deployment remains outside this authorization.

## Confirmed boundaries

- Ordinary task; do not create, focus, or modify a Pi goal.
- Claude Code (all managed profiles), Codex, Antigravity, and Pi.
- Upstream v0.1.0, commit `b3a35956759bf7f024af2ff061b2e0b44b438e4c`.
  GitHub annotated-tag API and fetched checkout agree. Release notes do not
  certify exact-artifact live-host tests; Pi is not upstream-supported.
- Complete bundle: skills, personas, standards, docs, assets, and licenses.
  No skills-only installation and no upstream text fork.
- Existing structured questions, human approvals, requested language, governance
  preconditions, permissions, model/provider/effort and tooling rules take priority.
- Approved retirements: third-party `to-spec` (keep local `to-prd`) and only
  `grilling:handover` (keep governance successor, `grit-grill`, and plugin).
  Preserve other skills: code-diff review, alternative API design, safe refactor
  commits, governance and tracker publication are not replaced by EGM.
- Main stays on main; write only in this worktree. Push/PR publication is
  authorized; squash merge requires all applicable CI to pass on the exact head.
  No broad skill/plugin updates, live deployment, permission/model changes or
  system setup.
- Private skills are included in investigation. Keep private identities/content
  and evidence outside the public repository/PR. No private edit is assumed.

## Changes and contracts

1. `dump/harness/claude-plugins.json`: add `egm` pinned to v0.1.0 and `egm@egm`.
   All existing declarations remain unchanged.
2. `dump/harness/pi-packages.json`: add the native pinned git package. The full
   clone retains sibling resources; Pi conventionally discovers seven commands.
3. `scripts/install_pi_extensions.py`: add targeted `--egm-only` mode to the
   existing CLI, not a new Python tool. It installs ONLY EGM and its guide and
   reviewer: no npm packages, unrelated templates/extensions, retired-package
   removals, global updates, Ollama or machine bootstrap. Pass the chosen
   PI_CODING_AGENT_DIR to native Pi children. Preserve user settings including Bun.
   A missing configured EGM clone gets its own native install. A present checkout
   must have approved HEAD, required runtime files and clean tracked content,
   with no untracked additions (including ignored files), before and after
   native installation. Wrong-ref/incomplete/dirty/extra-file clones fail with
   recovery advice, not silent reset. Reject skip-worktree/sparse and
   assume-unchanged index entries too. Re-verify after any general npm recovery.
   Verify after install too. Default deployment retains existing general behavior,
   except EGM must not be treated as a missing npm package.
4. `scripts/claude_plugins.py --egm-only`: select ONLY EGM marketplace/plugin;
   no unrelated marketplaces/plugins/disabled/retired migrations or LSP probes.
   Existing inventory/reconciliation and home ownership remain authoritative.
5. `config/pi/agents/egm-reviewer.md`: native read/search/list-only profile;
   no ambient extensions, inherited skills/project/global context, memory,
   model/effort override or nested delegation. Parent writes reports and fixes.
6. `ROOT_AGENTS_docs_agents_egm.md`: on-demand compatibility guide. Resolve
   plugin resources from the discovered active skill root, references from its
   directory, artifacts from the workspace. Preserve staged approvals/order;
   map question payloads to native structured UI, retaining local policy.
   Pi dispatches directly through the dedicated reviewer with explicit
   `options.context: fresh`. Inspect effective native get/list capabilities,
   project/user overrides and required host child extensions before dispatch.
   Refuse substituted profiles, extra tools/context/skills, unexpected route or
   effort, and extensions whose isolation is unknown. Required host extensions
   survive `extensions: []`; do not promise that field is a sandbox.
   Persona/target/standard paths and completed required reads are mandatory.
   Claude must be 2.1.271 or later for omitClaudeMd; older/unknown versions
   stop Goldfish dispatch, not merely gain trust through installed adapters.
   Profile installation alone is NOT Goldfish-isolation evidence. If effective
   preflight/actual child evidence is unavailable, stop and report unverified.
   Bootstrap docs are written in the parent; scouts use the read-only profile.
   Existing governance gates precede EGM readiness; do not name private gates.
7. `ROOT_AGENTS.md`: one EGM-triggered spoke pointer. Existing sync owns its
   distribution to Claude/Codex/Gemini. Pi's installer places the same spoke in
   its agent directory and maintains ONLY a marked EGM pointer in AGENTS.md.
   Preserve other user text; refuse malformed markers and user-owned guide/agent
   collisions. Place guide before context pointer. No home skill copies.
8. `justfile`: `egm-install` explicitly runs `sync-agents all` first, then the
   two targeted installers, native Codex marketplace/add with v0.1.0, verifies
   Pi's source again, and native Antigravity local-bundle installation. This
   sync prerequisite uses existing hook/settings ownership and is documented;
   it is not run on live homes pre-PR. Never compose full plugin/package
   installers, guess agy URL ref syntax, write plugin caches, or delete skills
   automatically. Targeted native model-free rehearsals do not run this recipe.
9. `dump/harness/skill-lock.json`: remove only to-spec. Placement does not prune
   old stores: document successor discovery first, targeted CLI retirement, then
   consumer verification. Never dump/adopt unrelated live-machine hash drift.
10. Delete `plugins/grilling/skills/handover/SKILL.md`; update grilling README,
    plugin manifest and root marketplace descriptions/versions together. Leave
    grit-grill bytes unchanged; document its governance successor by reference.
11. Regressions: `tests/unit/test_install_pi_extensions.py`, `test_claude_plugins.py`,
    and focused `test_egm_integration.py`. No gate weakening or dependency changes.
12. `docs/runbook/egm.md`, `docs/agent-sync.md`, `README.md`: installation, invocation,
    ownership, precise deletion list, successor-first migration, limitations.
    hironow/skills source stays unchanged: no redundant local skill was proven.

## Verification and stopping point

- Red before implementation: pins/declarations/retirements; missing clone install;
  wrong-ref/incomplete/dirty/untracked (including ignored) rejection; explicit
  child agent-dir propagation; minimum Claude isolation version;
  targeted paths cannot call unrelated installs, retirements, templates, LSP
  probes, updates or bootstrap; general npm-only reconciliation; user context
  preservation/idempotence/collisions/malformed markers; static reviewer fields.
- Green: targeted tests, Ruff format/check, ty, `just check`, full unit gate,
  `just skills-lock-check`, `just instruction-budget`, and `just lint-claude`.
  Fix causes, do not weaken checks. Save actual output and report exact status.
- Recipe changes require `just test`. Docker executable is absent (OrbStack link
  is dangling) and Podman is unreachable. Attempt the gate; report blocked,
  never passed. Do not start/install system software. PR CI has not run pre-PR.
- Four native model-free rehearsals have succeeded in isolated homes: targeted
  Pi git install, Claude add/install, Codex add/install, agy local install after
  proving temporary HOME list was empty. Pi settings selected Bun and disabled
  telemetry beforehand. All five runtime trees and LICENSE match the pinned
  source byte-for-byte; Claude adapters match too. Pi offline RPC sees all seven
  commands. These do NOT prove end-to-end workflow or fresh-context isolation.
- Native isolation needs effective-definition preflight and actual child/session
  evidence. If not exercised, say unverified; do not retire any live predecessor
  based on installation alone. Never simulate Goldfish in the parent.
- Mandatory independent plan review before implementation and final diff review.
  Parent checks quoted findings against source and executed checks.
- Publication: preserve the accepted full tree while splitting structural and
  behavioral commits. Run normal signed commits and hooks; never bypass a gate.
  Scan the public PR body, create the PR, mark it ready for CI, and observe the
  exact head's full check results. Merge with an exact-head guard only after all
  applicable CI succeeds. Report PR, commit/merge identities and remaining
  runtime limits; do not deploy live agent homes.

## Investigation and review evidence

- Initial independent conflict inventory: `d60430e9ee717f12ef28e5ba1f478e921`.
  It disclosed incomplete EGM reads. Supplemental independent inventory
  `df4814d64d4d52dc56c463a956bd64458` fully read the remaining four skills,
  all nine agents/five standards, and the grilling payload. It found no further
  EGM replacement and the handover duplicate subsequently approved by the owner.
- Quantitative `just compare to-prd <installed-to-spec>`: 79/75 lines,
  20 body-diff lines, no tooling violations. Parent checked both source texts.
- First plan review `dc2217957dcd73e57e60671f49a898e55`: REVISE. Parent verified
  all five findings. Targeted modes address unrelated bootstrap; explicit sync
  addresses missing guidance; effective-agent preflight addresses overrides and
  required extensions; native byte comparison addresses artifact coverage;
  isolated Bun settings address package-manager defaults. The reviewer disclosed
  incomplete upstream/Claude reads, so re-review must complete those contracts.
- Second review `d5f79a935b66ce9457d81feca667cf50e`: completed all requested
  source-contract reads; the previous five findings were addressed at plan level.
  Two remaining bounded corrections were incorporated: reject all added files,
  including ignored additions, and require Claude >=2.1.271 for Goldfish dispatch.
- Final plan correction check `db7d043c62fc2bf32a3a43c23a3a86ff9`: APPROVE
  (textual plan only).
- Initial implementation review `dc6ad04c8beeca48a122ebcfafa57fb08`: two P2
  corrections. Parent reproduced both: npm recovery could move EGM after the
  last check; index flags could hide missing/modified skill references with
  clean status. Three regression cases failed first, then passed after adding
  post-recovery verification and rejecting non-H `git ls-files -v` entries.
- Related tests now 148 passed, including the owner-approved fixture-only fix
  for hardcoded Linux cp/chmod paths (untouched main reproduced the failure;
  production clipboard code is unchanged).
- First full pass: `just check`, Claude validation, budget 31/40, skill declaration
  succeeded; unit had only the pre-existing clipboard fixture failure, now fixed.
  Sandbox `just test`: 15 host checks passed, 111 Docker fixture errors
  (`PermissionError: docker`); not a sandbox pass. No daemon/software was started.
- Isolated native targeted Claude installer succeeded twice. Native grilling
  update 0.2.1→0.3.0 retained grit-grill and removed the handover entry point.
- Final bounded integrity review `d75fb6e74fb4491cb752afe8411c43ba7`: APPROVE;
  both implementation findings closed. Independent fixture-only review
  `dc4dcdcebe94d16c4cb36a2274f121cd4`: APPROVE. These are read-only reviews,
  not runtime isolation or native Windows execution proofs.
- Final gate `bb1052372` exited 0 after the integrity corrections: `just check`
  (including Ruff, ty, Semgrep and Go tests), `just test-unit` (1,949 passed,
  106 skipped), `just lint-claude`, `just instruction-budget` (31/40),
  `just skills-lock-check`, staged confidentiality scan (11 tokens), whitespace.
  Claude's existing icon/README advice did not change its validation verdict.
- Docker sandbox remains blocked as above. Full EGM interactive workflows,
  actual Goldfish child isolation and PR CI are unverified. No live predecessor
  was removed; its safe migration is documented for adoption after review.
- Live stores, plugins, instructions, models and permissions are unchanged.
