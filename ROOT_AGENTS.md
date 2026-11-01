<!--
  AGENTS.md: cross-tool agent instructions. Codex, Cursor, Copilot, Claude Code
  (through @import), and other tools read it. Keep it SHORT; it is always loaded.
-->

# AGENTS.md

This is production code for an agentic engineering ecosystem. One person runs it
on GCP and supervises the agents as the human on the loop. New code is Go (Rust
when Go does not fit); existing Python and TypeScript tooling stays where it is.
Change things carefully: make the smallest correct change, prove it works, and
leave every check green.

When instructions conflict, the file closest to the edited file wins. An
explicit instruction in the chat overrides everything here.

## Rules you must not break

Hooks, pre-commit, and CI enforce these rules (see Enforcement). Each rule gives
its reason so you can apply it to cases a check does not list.

- **Python uses `uv`, `ruff`, and `ty`. No substitutes.** Use `uv` to install
  and run (`uv sync`, `uv add`, `uv run`). Never use `pip`, `poetry`, or
  `pipenv`: two resolvers put the lockfile out of sync. Use `ruff` to lint and
  format, and `ty` (astral-sh/ty) to check types. Never use `mypy`, `pyright`,
  `flake8`, `black`, or `isort`. One toolchain, one config, one gate.
- **New code is Go, newest stable; Rust only when Go does not fit.** Write new
  services, CLIs, and tools (and the control plane) in Go, not Python,
  TypeScript, Ruby, shell, C++, or Java. The one exception is GPU work that
  targets CUDA, through PyTorch or another CUDA library, which may be Python.
  Ship one binary per OS and CPU so the same tool runs on every device. Go 1.27
  is the minimum; use the newest stable Go the module compiles with. Use Rust
  only for no-GC, tight-memory, or WASM targets, or an existing Rust codebase.
  Wanting more speed is not a reason by itself: measure first
  (docs/agents/rust-tooling.md).
- **Use few dependencies; use the standard library first.** In every language,
  use the official standard library before a third-party package, and use its
  newest features and methods. A third-party package needs a reason the
  standard library cannot meet. Fewer packages mean less supply-chain risk and
  fewer upgrades.
- **Never use LiteLLM, in any repo or language.** Its PyPI release channel
  shipped credential-stealing malware twice in 2026 within hours, faster than
  any cooldown window can cover. Call a provider SDK directly. Existing uses are
  removed, not extended.
- **Use only `bun` for Node.** Never use `npm`, `yarn`, or `pnpm`, including
  `corepack pnpm`. The reason is the same: lockfiles go out of sync.
- **`just` is the only task runner.** Keep exactly one `justfile`, at the repo
  root. No `justfile` in subdirectories, and no `make`. One entry point means
  one place to look.
- **Use `.yaml`, never `.yml`.** Name Compose files `compose.yaml` (Compose
  Spec v2+). `docker-compose.y{a,}ml` is the old v1 name. One spelling stops
  tools from missing files and stops review churn.
- **Never change infrastructure managed as code (IaC) by hand.** Change production (GCP,
  IAM, Cloud Run, cloud VMs, clusters) only through OpenTofu, a PR, and CD. A
  stray `gcloud ... update` creates drift, and the next `tofu apply` silently
  reverts it.
- **Never weaken a check to make it pass.** Do not edit ruff, ty, semgrep, or
  golangci config to hide a finding. Never commit with failing tests or with
  lint or type findings. Fix the cause.

## Main commands

Run `just` to list the repo's tasks. `just check` is the full local gate for
every language in the repo.

If you need a command that is not a `just` task, add it to the root `justfile`.
Do not write a one-off script.

## When principles conflict

1. Safety and correctness come before performance.
2. Passing tests come before elegant code.
3. Readable code comes before short code.
4. Explicit comes before implicit.

If you are unsure, write a test that pins down the requirement before you code.

## How to work (Tidy First, TDD, YAGNI, KISS, DRY, SOLID)

- Start every change with a failing test: **Red → Green → Refactor.** Write
  only enough code to pass. Refactor only when tests are green.
- **Keep structural and behavioral changes in separate commits (Tidy First).** Commit the
  structural change first. The Conventional Commit *type* says which kind a
  commit is, so one commit never mixes types.
- **Build only what is needed, as simply as possible.** YAGNI: build only what a
  current requirement or test asks for. KISS: choose the simplest design that
  works. DRY: keep each piece of knowledge in one place, but do not merge code
  that only looks alike. SOLID: give each unit one reason to change, and depend
  on ports (purpose-named interfaces; see Design), not on concrete adapters.
- **Scope file searches to the task.** Search the current project or named,
  task-relevant directories. Ask for explicit approval before recursively
  scanning a filesystem root (`/` or a drive root), an entire home directory,
  or unrelated protected data, including through wrappers or scripts. Narrow
  the search instead of granting extra OS permissions: broad scans can trigger
  permission prompts attributed to the terminal app.
- **Name things specifically.** Choose the name that says what the thing does
  in this domain. Do not use generic words such as `Manager`, `Helper`, or
  `Util`.
- **Check before you say it is done.** Run `just check`. Report the results
  honestly, including failures.

## Design (functional core, imperative shell, ports and adapters)

- **Keep the core pure.** Business logic takes values (including the current
  time) and returns values. It does no I/O and calls no port. The shell reads
  through ports, calls the core, and writes the result through ports.
- **Reach the outside only through ports.** A port is an interface named for
  its purpose (`Mailer`, not `SMTPClient`). Each technology gets its own
  adapter; changing a technology never changes the port.
- **Every external service gets a fake in `fake/`.** A fake is a small working
  in-memory version of the port. Tests and local runs use fakes by default; a
  real adapter needs explicit configuration, so nothing calls a real service by
  accident.

## GRIT (required both ways: show it yourself and demand it of others)

GRIT = Guts (度胸) / Resilience (復元力) / Initiative (主体性) / Tenacity (執念).

- **Guts**: do the scariest, least-known part first, and say plainly what you
  do not know.
- **Resilience**: when something fails, change your hypothesis and try again.
  Never stop or hand back half a result.
- **Initiative**: take the obvious next step without being asked, but still
  confirm actions that cannot be undone or are out of scope.
- **Tenacity**: define "done" in concrete terms and keep going until you
  reach it. Never claim success you have not proven.

Stop and press for a concrete commitment when resolve is weak: an unclear
finish line, an unknown nobody has faced, or a gap where someone is "waiting
on someone else". Record risks nobody has committed to in docs/handover.md.
When you delegate, demand a definition of done, a way to recover from failure, and
proof of completion. Scoring rubric (1-5): the `grilling:grit-grill` skill.

## Documentation rules (short version)

- **Write in plain language, in every language.** Put the main point first, use
  short sentences, the active voice, and common words. This covers docs, code
  comments, commit and PR text, and answers.
- `docs/*.md` describe the system as it is **now**. No history, no TODOs, no
  roadmap. An outdated doc is a bug: update docs in the same commit as the code.
- `docs/intent.md` says why we are doing this work now. A human writes it;
  never guess it, ask. `docs/handover.md` says where we are and what comes
  next; update it every session.

## Detailed guides: read when needed, not before

Open the matching file as soon as its trigger applies:

| When you are…                                  | Read                                |
| ---------------------------------------------- | ----------------------------------- |
| writing or changing Python                     | docs/agents/python-tooling.md       |
| writing or changing Go or a service            | docs/agents/go-tooling.md           |
| choosing between Go and Rust, or writing or changing Rust | docs/agents/rust-tooling.md |
| modeling distributed state / Quint            | docs/agents/formal-methods.md       |
| adding, bumping, or triaging a dependency      | docs/agents/dependency-policy.md    |
| writing a `pull_request` workflow              | docs/agents/draft-ci.md             |
| in the Red/Green/Refactor loop                 | docs/agents/tdd-workflow.md         |
| writing a commit message                       | docs/agents/commit-discipline.md    |
| naming a package, file, type, function, or variable | docs/agents/naming.md          |
| writing or placing tests / asking "mock?"      | docs/agents/testing.md              |
| converting a hand-rolled TypeScript test harness to `bun:test` | docs/agents/bun-test-migration.md |
| splitting code, calling anything outside the process, or adding a fake | docs/agents/core-shell-ports.md |
| adding telemetry, spans, or a service          | docs/agents/observability.md        |
| touching `tofu/`, `gcloud`, `kubectl`, Cloud Run | docs/agents/iac-drift-policy.md   |
| creating a GCP storage sink, build, or compute that runs unattended | docs/agents/gcp-cost-guardrails.md |
| adding or maintaining a Semgrep rule           | docs/agents/semgrep.md              |
| editing docs / writing an ADR / intent / handover | docs/agents/docs-discipline.md   |
| creating dirs or files, or unsure where code goes | docs/agents/project-structure.md |
| blocked by a hook, or scanning a repo for banned patterns | docs/agents/enforcement.md |
| using the `rtk` output-filter proxy / debugging filtered output | docs/agents/rtk.md |
| using headroom (its MCP tools, the j-cc proxy, its egress)      | docs/agents/headroom.md |
| adding, comparing, retiring, or distributing a skill (hironow/skills, `skill-lock.json`) | docs/agents/skills-maintenance.md |
| invoking an EGM design, review, or documentation workflow | docs/agents/egm.md |

## Enforcement (works no matter what the model decides)

A block is policy, not a suggestion. Read the reason and change your approach;
never work around it. Layers, the exit-code contract, and what each hook covers:
docs/agents/enforcement.md.
