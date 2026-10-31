# Skills maintenance

Read this when you add, compare, retire, or distribute a skill (`hironow/skills`
or third-party skills in `dump/harness/skill-lock.json`).

## Where skills live and how they reach agents

- **hironow/skills** holds self-authored skills and forks with local changes
  (branch → PR with `just check` → squash merge).
- **`~/.agents/skills` (the store)** holds every skill, installed by
  `bunx skills` (`-a universal` so the CLI writes only the store) and declared
  in `dump/harness/skill-lock.json` (dotfiles ADR 0043). Pi reads the store
  directly.
- **Consumer homes** (`~/.claude*`, `~/.codex`, `~/.gemini`) get relative
  symlinks (or tracked copies) into the store via `just skills-place`. Never
  edit a skill inside a home; edit in its source repository.
- **hironow/skills wins name collisions**: `just skills-lock-check` (in `just ci`)
  enforces this, and `just restore-skills-lock` installs `hironow/skills` last.
- **Private skills** never go into `hironow/skills` or `skill-lock.json`
  (`just dump-skills-lock` excludes private sources via `gh` and fails closed if
  visibility cannot be verified). Install private skills per machine with
  `bunx skills add <repo> -g -s <name> -y -a universal` and link them manually.

| repo | command | purpose |
| --- | --- | --- |
| hironow/skills | `just check` | frontmatter, links, fences, provenance contract, README sync |
| hironow/skills | `just audit-consumers` | every home resolves each skill to checkout-identical bytes |
| hironow/skills | `just compare <fork> /abs/<upstream>...` | size, description, tooling violations, and body diff |
| dotfiles | `just dump-skills-lock` | update `skill-lock.json` from store (refuses silent self-drop unless `--allow-self-drop`) |
| dotfiles | `just restore-skills-lock` | new machine: install declared skills into store, then place |
| dotfiles | `just skills-update` | `skills update -g -y` on store, then re-place homes |
| dotfiles | `just skills-place` | (re)link homes (`--force` replaces differing dirs, `--copy` forces copies) |

Use `SKILLS_LOCK_HOME=<dir>` for a rehearsal in a separate home.

## Provenance contract (derived skills)

A skill derived from upstream work carries this frontmatter:

```yaml
license: Apache-2.0                          # SPDX id of the license we redistribute under
metadata:
  provenance: derived                        # derived | original | unknown (absent = unknown)
  upstream: owner/repo@<sha>:<path>          # the compared upstream revision and skill path
  upstream-license: Apache-2.0               # the license that applies upstream (skill LICENSE.txt > repo LICENSE)
  changes: "one line on what changed here"   # quote it: a bare value must not contain ': '
```

- Keep the upstream `LICENSE*` file untouched in the skill directory.
- Add a first-line modification notice (`<!-- Modified from owner/repo@sha:path; ... -->`
  or `#` comment) to every bundled file that differs from upstream.
- For gists, use `upstream: gist:<owner>/<gist-id>@<revision-sha>:<file>`. If
  origin is unknown, write `upstream: unknown`.
- Original skills use `provenance: original` (and optional `metadata.inspired-by`
  URLs separated by `; `). Run `just readme-index` and `just audit` in
  `hironow/skills`.

## Comparing a fork with its upstream (dedup procedure)

1. **Fetch, do not install.** `git clone --depth 1` upstream into a scratch dir.
   Never run `bunx skills check` or `update` before comparing.
2. **Quantitative pass.** In `hironow/skills`, run
   `just compare <fork> /abs/<scratch>/<upstream-skill>`.
3. **Independent judge.** Give a read-only model both files with the judge
   prompt below. Verify every quoted line against the files before acting.
4. **Decide**: `KEEP_FORK` / `PORT_UPSTREAM_INTO_FORK` /
   `REPLACE_FORK_WITH_UPSTREAM` / `KEEP_BOTH_DIFFERENTIATE` (edit only the
   fork's description).
5. **Execute (place successor → verify consumers → retire old copy)**:
   - keep/port: merge in `hironow/skills`, run `just skills-update`, retire
     upstream with `bunx skills remove -g <upstream-name> -y`, then run
     `just dump-skills-lock` and `just skills-place`.
   - replace: `bunx skills add <repo> -g -s <name> -y -a universal`, delete fork
     in `hironow/skills` (PR, merge), then run `just skills-update` and
     `just dump-skills-lock --allow-self-drop`.
   - verify: `just skills-place` (0 kept, 0 missing) and `just audit-consumers`
     in `hironow/skills`.
6. **Confirm routing** with a fresh Pi session:
   `pi -p --tools read --no-session --model opencode-go/glm-5.3 "<routing prompt>" < /dev/null`.

### Judge prompt

```
You are an independent judge comparing two versions of the same agent skill. Read both files
(read-only): FORK <path>, UPSTREAM HEAD <path> (fetched <date>).
Rules: "newest" is not automatically "better"; the owner's tooling rules are uv only, bun/bunx
only, just as task runner, .yaml not .yml (a contradiction is a defect); text that only works in
one harness is a portability cost unless guarded.
Step 1 — capability inventory: every capability, phase, or output each version provides, marked
FORK-only / UPSTREAM-only / both.
Step 2 — score both 1-5 with a quoted line per score: trigger precision, step specificity,
progressive disclosure, environment fit (name every external skill/command dependency),
verification discipline, writing quality.
Output: inventory table; scores table; upstream improvements worth porting (quoted, where they go);
fork adaptations worth keeping (quoted); defects in either (quoted + fix); verdict — exactly one of
KEEP_FORK | PORT_UPSTREAM_INTO_FORK | REPLACE_FORK_WITH_UPSTREAM | KEEP_BOTH_DIFFERENTIATE — with the
inventory items that would be lost; then the same as JSON. Do not invent content not in the files.
```

### Routing dry-run prompt

```
Answer in ONE message from the <available_skills> list already in your system prompt. Do NOT call any
tool; this is a routing dry-run, not a task. For each request name the SINGLE skill you would invoke
first (exact skill:<name> or "none"), the runner-up if one was a close candidate (or "-"), and one
sentence why. Requests: 1. "..." 2. "..." ... Output a markdown table: # | chosen | runner-up | why.
```

## Rewriting a skill in another language

Write instructions in English; keep the reader's language for Japanese-writing
skills and human-facing templates/outputs. After a rewrite, run a read-only
model fidelity check comparing original and rewrite for semantic differences
(omission, addition, meaning change, reference break) and fix every medium/high
finding before merging.
