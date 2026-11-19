# Installing and using EGM

Elephant-Goldfish Model (EGM) is a plugin that creates design documents and has separate agents without conversation history review them.
It never replaces implementation edits, tests, or human approval.

## Pinned versions and placement

The installed version is pinned to a `google/elephant-goldfish-model` release tag. The tag is sourced from `egm` in `dump/harness/claude-plugins.json`, the commit from `EGM_COMMIT` in `scripts/install_pi_extensions.py`, and other pins match those.
Because copying skills alone omits personas and standards read at runtime, the full bundle is installed.

| Environment | Placement owner | Declaration |
| --- | --- | --- |
| Claude Code | Native plugin CLI; targets each existing Claude home | `dump/harness/claude-plugins.json` |
| Codex | Native marketplace and plugin CLI; pinned with the same `--ref <tag>` as Pi's pin | `scripts/codex_agy_plugins.py` (`just deploy`) |
| Antigravity | `antigravity plugin install` (formerly `agy`); receives the verified Pi bundle | `scripts/codex_agy_plugins.py` (`just deploy`) |
| Pi | Native git package; discovers the 7 skills inside the bundle | `dump/harness/pi-packages.json` |

The Pi bundle lives at `<PI_CODING_AGENT_DIR>/git/github.com/google/elephant-goldfish-model`.
The default agent directory is `~/.pi/agent`.
For existing clones, the installer checks the pinned commit, required files, modified tracked files, and untracked files (including ignored ones).
It also rejects index states that hide changes or missing files, such as sparse checkout, skip-worktree, and assume-unchanged.
When the regular installer restores other packages, it checks EGM again afterward.
On mismatch, it stops rather than wiping user edits with reset or delete.

## Installation

There is no standalone EGM install command.
`just deploy` installs it alongside other plugins in order: Pi (`install_pi_extensions.py`), Codex and Antigravity (`codex_agy_plugins.py`), and Claude Code (`claude_plugins.py`).
Codex and Antigravity follow Pi's pin and are skipped on machines without their CLIs.
Codex is a no-op if its commit and version already match Pi's pin; when the tag moves, it removes and re-adds the marketplace (because Codex retains the initial marketplace ref).
Antigravity checks the egm version via `antigravity plugin list --json` and installs the verified bundle only on mismatch (replacing the installed one). If the version matches but is disabled, it enables it; if the list cannot be read, it reinstalls.
A failure in one step emits WARN and continues the rest; incomplete environments are never reported as successful.
Restart each CLI before using it.

To change versions, run `just agent-bump egm [tag]` (ADR 0074).
If required files are missing in the new tag (an upstream layout change), it stops without writing anything.
That version cannot be bumped with `just agent-bump`.
Updating only the required-files list in `scripts/install_pi_extensions.py` first would cause the currently installed bundle to fail pre-checks.
Instead, update the required-files list and the four pins (`dump/harness/claude-plugins.json`, `dump/harness/pi-packages.json`, `EGM_SOURCE`, `EGM_COMMIT`) together in one PR.
After merging, run the installers from the `main` checkout in the same order as `just deploy` (Pi, Codex and Antigravity, Claude Code).
To roll back, `git revert` that PR and run the same installers.

The existing installer places Pi supplementary files: `docs/agents/egm.md` and the `egm-reviewer` profile.
To the global context file selected by Pi's precedence, it adds only a reference wrapped in EGM markers.
It preserves user text and never overwrites broken markers or same-named guides/profiles owned by others.
Symlinked context files are not edited either; the owner must resolve them.

## Invocation

| Purpose | Skill name |
| --- | --- |
| Exploring problems and options | `egm-brainstorm` |
| Drafting design documents | `egm-draft` |
| Reviewing design documents | `egm-review` |
| Adjudicating findings | `egm-resolve` |
| Handling individual review passes | `egm-review-loop` |
| Creating README contracts | `egm-bootstrap` |
| Detecting drift between design docs and implementation | `egm-drift-report` |

In Claude, invoke as `/egm:egm-brainstorm`.
In Codex, pick an installed skill; in Antigravity, invoke as `/egm-brainstorm`.
In Pi, invoke as `/skill:egm-brainstorm`.

The source of truth for supplementary guidance is [`ROOT_AGENTS_docs_agents_egm.md`](../../ROOT_AGENTS_docs_agents_egm.md).
Existing question UIs, approvals, the requested output language, and local pre-execution gates take precedence.
Do not treat EGM readiness or uninterrupted mode as substitutes for those approvals.
Confirm user instructions when moving from design work to implementation as well.

## Review isolation requirements

Claude requires **2.1.271 or newer**, which supports `omitClaudeMd`.
Stop Goldfish launches on older or unknown versions.
In Codex and Antigravity too, ensure a fresh conversation context using the actual native tool available.

Pi is not an officially supported upstream target.
Having the `egm-reviewer` file alone does not prove isolation.
Inspect the effective profile, project/user overrides, host-required child extensions, and actual launch info.
Even with `extensions: []`, host-required extensions can remain active.
Always pass `options.context: "fresh"` on every invocation.
If you cannot verify no extra permissions, conversation history, or model/effort changes leaked in, stop the review and report it unverified.

A child that failed or could not finish reading personas, standards, or the target doc is incomplete, not "no findings".
A fresh conversation context does not imply a filesystem sandbox.
Verify with actual child/session evidence rather than relying on self-reports alone.

## Migrating overlapping skills

In public install declarations, keep `to-prd` (turn conversations into issue specs) and exclude `to-spec` (same workflow).
In `grilling` 0.3.0, expose only `grit-grill` and delegate handover creation to `intent-handover-governance`.
Keep `review` (code diffs), `design-an-interface` (comparing API options), and `request-refactor-plan` (safe step-by-step decomposition).
Their deliverables and workflows differ from EGM.

Removing an item from the declaration does not delete it from existing machine stores.
Follow this order when migrating:

1. Verify in a new session that the 7 EGM entry points plus `to-prd` and `intent-handover-governance` are discoverable.
2. Verify each linked consumer can read the successor. Startup checks alone do not count as verifying Goldfish execution.
3. Retire only `to-spec` from global scope using the skills CLI (e.g., `just skills remove -g to-spec -y -a universal`). If the CLI stops, abort rather than wiping the store or all skills in bulk.
4. From `main` after merge, run native `claude plugin update grilling@hironow-plugins` in each Claude home, and confirm 0.3.0 and `grit-grill` exist while the old handover entry point is gone.
5. Check consumers for stale copies or dangling links; report user-edited copies instead of deleting them automatically.

`just deploy` and `just agent-bump` do not automate this retirement.
Also, never dump the entire live lockfile just to update declarations, which pulls in unrelated hash drift.

## Verification scope

Tests live in `tests/unit/test_egm_integration.py` and the existing unit suites for both installers.
They check declarations and pins, bounded installer side effects, clone rejection rules, context preservation, and static profile constraints.

Installation, discovery of the 7 commands, and file parity with the pinned version are separate from proving interactive design flows or review isolation at runtime.
Upstream releases also do not guarantee behavior across all hosts for the distributed ZIP itself.
Report PR CI, real-host questions and approvals, and native child isolation strictly for the scope actually tested.
