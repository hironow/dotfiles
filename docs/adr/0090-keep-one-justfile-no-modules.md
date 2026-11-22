# ADR 0090 — Keep one justfile; do not split it into just modules now

- **id**: ADR-0090
- **title**: Keep one justfile; do not split it into just modules now
- **status**: Accepted
- **date**: 2026-11-23
- **decided-date**: 2026-11-23
- **decision-maker**: Hiroto N.
- **decision-maker-contact**: @hironow
- **author**: Claude Code (owner session)
- **author-contact**: @hironow
- **supersedes**: none
- **superseded-by**: none
- **related**: [0089](0089-dev-container-tests-off-pull-requests.md)
- **consultation-trace**: the owner's request in a Claude Code session on 2026-11-23 ("group や doc や mod なども…整理してください"); the plan and its three Codex reviews are in the PR

## Plain summary

The owner asked to bring the justfiles, the template and the instructions in line with the latest `just` (1.59.0), and to organise groups, docs and modules the same way.
Groups, docs, the canonical format and script recipes are done (#671, #672, #673).
Splitting the root justfile into `mod` modules is possible, but it costs a rule change and work in many places for little gain now that `just --list` is grouped by purpose.
This record proposes keeping one justfile, and says when to split.

## Context

- The root justfile has about 2700 lines and about 220 recipe headers. Since #672 every public recipe is in one of 15 groups with a one-line doc, so `just --list` reads by purpose.
- The global rule says "Keep exactly one `justfile`, at the repo root. No `justfile` in subdirectories" (ROOT_AGENTS.md). `mod` loads other files (`<name>.just`, `<dir>/mod.just`), so using it changes that rule for every repository that follows the instructions.
- just 1.59.0 facts, checked on scratch justfiles and by Codex in the plan reviews:
    - A recipe in a module is called as `just emulator up` or `just emulator::up`. The old name can stay as `alias emu-up := emulator::up`, but an alias can be neither a dependency nor another alias's target (`ci` depends on `emu-lint`; `alias emu-up-lite := emu-up` exists).
    - Each module has its own settings (`shell`, `script-interpreter`, `default-list`, `positional-arguments`) and its own variables; a module recipe runs in the module file's directory unless the module sets `working-directory`.
    - `just module` runs the module's first recipe unless the module sets `default-list`.
    - `just --fmt --check` on the root does not check the module files.

## Decision (proposed)

- D1. The root justfile stays the only justfile. No `mod` and no `import` for now.
- D2. Revisit when one of these holds: a domain needs settings the rest must not have (another shell, `dotenv`), the justfile passes 4000 lines, or a group's recipes are mostly called by another repository.
- D3. When splitting, follow the design under "Option B" below, and change the global rule in the same record.

## Options considered

- **A. Keep one justfile (proposed).** Cost: none. `just --list` is already grouped; recipe names keep their `emu-` / `tel-` / `tailnet-` prefixes.
- **B. A pilot module for the emulator stack (31 `emu-` / `tel-` / `tailnet-` recipes).** What it would take, measured on main `3c4386e1`:
    - a rule change: "one entry point, the root justfile; it may load `just/<name>.just` with `mod`; no standalone justfile elsewhere", in ROOT_AGENTS.md and the project-structure spoke, synced to every agent home;
    - a shared `just/common.just` imported by the root and each module for the settings and the tool variables (`UV_RUN`, `JUST_FMT`, ...), and `set working-directory := ".."` and `set default-list` in each module;
    - `ci`'s dependency and the existing `emu-up-lite` alias pointed at `emulator::...`; private aliases for the old names people type; wrapper recipes where a dependency needs an old name;
    - the format gate and `just fmt` run on every `just/*.just`, with a test that an unformatted module fails it;
    - 11 test fixtures that copy or rewrite the justfile copy the module and shared files too; 3 test files that read emulator recipes read the module file;
    - docs that name `just emu-...` (AGENTS.md, runbooks) checked against the aliases.
- **C. Split every domain into modules.** Option B's cost for each domain, and the 66 test files that read the justfile.

## Consequences

- No change in how recipes are called; nothing to migrate.
- The rule "exactly one justfile" stays as written.

## Reversal

Accepting option B later is a new record that supersedes this one.

## Consistency with other decision records

- No record decides on `mod`; ROOT_AGENTS.md's one-justfile rule is unchanged by this record.

## Decision (2026-11-23)

- [x] Accept A / [ ] Accept with changes / [ ] Reject / [ ] Defer
- Decision-maker and date: Hiroto N. (@hironow), 2026-11-23 05:45 JST. Shown Claude's recommendations (accept ADR-0089 with the dev container tests running on the pull requests that can break them; ADR-0090 option A; register the gates as required checks with branches up to date; no organization move; no faster runners), the owner answered "では、全て推奨で進めましょう！！" (translated: then let us go with all the recommendations).
- Action: none beyond this record; the root justfile stays the only one.
