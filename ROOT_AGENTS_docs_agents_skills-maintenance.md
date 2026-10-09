# Skills maintenance

Read this when you add, compare, retire, or distribute a skill. That covers
hironow/skills, and any installed third-party skill that overlaps with one of
ours. The conventions for the skills themselves, and the tooling that checks
them (`scripts/`, `tests/`, `justfile`, CI), live in hironow/skills. This file
covers the procedure around them and how skills reach the agent homes
(ADR 0043).

## Where skills live and how they reach agents

- **hironow/skills** (a normal clone, e.g. `~/ghq/github.com/hironow/skills`)
  holds self-authored skills and forks that carry a deliberate local change.
  Changes go branch → PR (`just check` locally and in its CI) → squash merge.
  dotfiles holds no copy of it.
- **`~/.agents/skills` (the store)** holds every skill, ours and third-party.
  The `bunx skills` CLI installs them, and dotfiles declares them in
  `dump/harness/skill-lock.json` (`source: hironow/skills` for ours). pi reads
  the store directly. Only ever ask the CLI to write the store
  (`-a universal`).
- **Consumer homes** (`~/.claude/skills`, `~/.claude-work-{a..d}/skills`,
  `~/.codex/skills`, `~/.gemini/skills`) hold relative symlinks into the store.
  `scripts/skills_lock.py place` (`just skills-place`) places them; where the
  OS refuses symlinks, it places a tracked copy. Never edit a skill inside a
  home: the tool keeps and reports a differing real directory, and the CLI's
  own `update` would overwrite it. Edit in the repository.
- **hironow/skills wins a name collision** with a third-party skill: `dump`
  keeps our record, `check` fails on a collision, and `restore` installs ours
  last and repairs a store entry whose source is not ours.

## Gates and recipes

| command | what it proves / does |
| --- | --- |
| in hironow/skills: `just check` (`audit`, `readme-check`, tests, ruff, ty — the same uv/ruff/ty trio, pinned in that repo's own pyproject) | frontmatter shape, links and anchors, balanced fences, no emoji, Japanese only in the allowed places, provenance contract, README tables in sync; its CI runs the same on every PR |
| in hironow/skills: `just audit-consumers` | every home resolves each skill to bytes identical to the checkout (through the links); no dangling symlinks |
| in hironow/skills: `just compare <fork> /abs/<upstream>...` | size, description, tooling-rule violations, and body diff of two or more versions |
| dotfiles: `just skills-lock-check` (in `ci`) | the committed declaration lets no third-party skill shadow a hironow/skills name |
| dotfiles: `just dump-skills-lock` | normalize the CLI's machine lock into the declaration; refuses to drop a hironow/skills record silently (`--allow-self-drop`) |
| dotfiles: `just skills-update` | after a hironow/skills merge or any upstream change: `skills update -g -y` on the store, then re-place the homes |
| dotfiles: `just skills-place` | (re)link the homes; idempotent; `--force` replaces differing real directories, `--copy` forces tracked copies |
| dotfiles: `just restore-skills-lock` | new machine: install every declared skill into the store (hironow/skills last), then place |

`SKILLS_LOCK_HOME=<dir>` points the script and the child CLI at another home,
for a rehearsal. A full rehearsal still belongs in a container.

## Provenance contract (derived skills)

A skill that started from someone else's work carries this in its frontmatter:

```yaml
license: Apache-2.0                          # SPDX id of the license we redistribute under
metadata:
  provenance: derived                        # derived | original | unknown (absent = unknown)
  upstream: owner/repo@<sha>:<path>          # the compared upstream revision and skill path
  upstream-license: Apache-2.0               # the license that applies upstream (skill LICENSE.txt > repo LICENSE)
  changes: "one line on what changed here"   # quote it: a bare value must not contain ': '
```

Rules for derived skills:

- Keep the upstream `LICENSE*` file in the skill directory and never edit it
  (Apache-2.0 and MIT both require it). For a public-domain dedication such as
  the Unlicense, bundle the text with a note on where the author declared it.
- Every bundled file that differs from the upstream revision carries a
  modification notice on its first line
  (`<!-- Modified from owner/repo@sha:path; ... -->`, or a `#` comment in
  scripts). Apache-2.0 section 4(b) asks for this.
- Write a gist as `upstream: gist:<owner>/<gist-id>@<revision-sha>:<file>`
  (take the revision from `gh api gists/<id>`, `history[].version`).
- If you do not know the origin, write `upstream: unknown` and say so in
  `changes`. Never guess an author.

A skill you wrote yourself gets `provenance: original` once that is confirmed:
the first commit was authored in-repo, no public copy is older than it, and
nothing in the cloned upstreams matches it. Without the key, the skill is
listed as "origin not yet confirmed". An original skill whose idea came from a
public post or article names it in `metadata.inspired-by` (URLs separated by
`; `), and the README lists it as idea credit. In hironow/skills,
`just readme-index` turns all this into the README credits block (one row per
upstream), and `just audit` rejects a derived skill whose contract is
incomplete.

Skills that must not be published do not belong in hironow/skills at all.
Personal ones go to hironow/skills-private; organisation-internal ones go to
that organisation's own skills repository. Both reach the homes like any other
source: `bunx skills add <repo> -g -s <name> -y -a universal`,
`just dump-skills-lock`, `just skills-place`.

## Comparing a fork with its upstream (the dedup playbook)

Start this when a skill of ours and an installed third-party skill answer the
same request (a routing dry-run names one as a close runner-up of the other).
"Newest upstream" is not automatically better: we removed cruft from our forks
on purpose.

1. **Fetch, do not install.** `git clone --depth 1` the upstream into a scratch
   directory. Never run `bunx skills check` or `update` before comparing: they
   rewrite the store copy of anything the CLI tracks, including forks it once
   installed.
2. **Quantitative pass.** In the hironow/skills clone, run
   `just compare <fork> /abs/<scratch>/<upstream-skill>` for size, description
   length, tooling violations, and diff size.
3. **Independent judge.** Give a read-only model both files with the prompt
   below (capability inventory first, scores with quoted evidence, one of
   four verdicts). Check every quoted line against the files before you act on
   a finding.
4. **Decide**: `KEEP_FORK` / `PORT_UPSTREAM_INTO_FORK` /
   `REPLACE_FORK_WITH_UPSTREAM` / `KEEP_BOTH_DIFFERENTIATE`. In the last case,
   edit only the fork's description: an edit to an installed skill is lost on
   reinstall.
5. **Execute in this order: place the successor → verify every consumer can
   read it → retire the old copy.**
   - keep/port: edit the fork in hironow/skills, PR, merge, then in dotfiles
     run `just skills-update` (store refresh + place). Retire the upstream
     install with `bunx skills remove -g <upstream-name> -y` (the default scope
     is the project, so `-g` is mandatory). Then run `just dump-skills-lock`
     and `just skills-place` (a removed store entry is reported as missing
     until the declaration drops it).
   - replace: run `bunx skills add <repo> -g -s <name> -y -a universal` (store
     only). Then delete the fork in hironow/skills (PR, merge), run
     `just skills-update`, and run `just dump-skills-lock --allow-self-drop`.
     Dropping our record is the intended outcome here, so say so explicitly.
   - afterwards: run `just skills-place` (0 kept, 0 missing) and, in the
     hironow/skills clone, `just audit-consumers`. Then confirm with pi (below).
6. **Confirm routing** with a fresh pi session (a session that already
   discussed the removed skill keeps naming it):
   `pi -p --tools read --no-session --model opencode-go/glm-5.3 "<routing prompt>" < /dev/null`.
   To see pi's own view of the installed skills, without a model call:
   `printf '{"id":"1","type":"get_commands"}\n' | pi --mode rpc --offline`.

### Judge prompt

```
You are an independent judge comparing two versions of the same agent skill. Read both files
(read-only): FORK <path>, UPSTREAM HEAD <path> (fetched <date>).
Rules: "newest" is not automatically "better"; the operator's tooling rules are uv only, bun/bunx
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

Run it before and after the change with the same requests. The evidence is a
same-purpose runner-up that disappears.

## Rewriting a skill in another language

Write instructions in English. Keep the reader's language for the
Japanese-writing skills and for anything printed or filled in for a person
(templates, assets, Slack messages, report formats, setup notices, quoted
trigger phrases). After a rewrite, run a fidelity check with a read-only
model: original vs rewrite, reporting only semantic differences (omission,
addition, meaning change, reference break) with both quotes and a severity,
and a verdict of FAITHFUL or NEEDS_FIX. Revert every medium or high finding
before merging.

## Before making hironow/skills public

1. Run `gitleaks git` and `trufflehog git --only-verified` over the full
   history.
2. Grep the tree and history for mention IDs, emails, internal hostnames, org
   names, and personal profiles.
3. Reconcile every derived skill's license obligations (LICENSE file kept,
   changes stated).

Report the results; do not change the visibility.
