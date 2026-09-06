# Skills maintenance

Read this when adding, comparing, or retiring a skill in the `skills/`
submodule (hironow/skills), or when an installed third-party skill overlaps
with one of ours. Conventions for the skills themselves are in the
submodule's README; this is the procedure around them.

## Where skills live and how they reach agents

- `skills/` (submodule) — self-authored skills and forks that carry a
  deliberate local change. Changes go branch → PR → squash merge in
  hironow/skills, then a gitlink bump PR here.
- `~/.agents/skills` + `dump/harness/skill-lock.json` — third-party skills,
  installed with `bunx skills` and declared in the lock. A lock-managed name
  must never reappear in the submodule (`just skills-lock-check`).
- `just sync-agents` copies each submodule skill into the agent homes
  (`~/.claude*/skills`, `~/.codex/skills`, `~/.gemini/skills`,
  `~/.agents/skills`; pi reads `~/.agents/skills` directly). The copy is
  **additive**: it adds missing skills and never overwrites or deletes. After a
  skill changes, refresh the homes by hand and verify with
  `just skills-audit-consumers`.

## Gates

| command | what it proves |
| --- | --- |
| `just skills-audit` | frontmatter shape, links and anchors, balanced fences, no emoji, Japanese only in the allowed places, provenance contract for derived skills |
| `just skills-audit-consumers` | every agent home holds a byte-identical copy of every skill; no dangling symlinks |
| `just skills-readme-check` / `just skills-readme-index` | the README index and credits tables match the frontmatter (check / regenerate) |
| `just skills-lock-check` | no lock-managed third-party name inside the submodule |
| `just skills-compare <fork> <upstream>...` | size, description, tooling-rule violations, and body diff of two or more versions |

`just ci` runs the lock check today; the audit and the README check join it
together with the submodule bump that brings the generated README. The GitHub
`skills` job then runs the same three against the gitlink; it checks the
private submodule out with the `SKILLS_SUBMODULE_TOKEN` secret and fails —
never skips — when the token is missing or the submodule comes back empty.

## Provenance contract (derived skills)

A skill that started from someone else's work carries, in frontmatter:

```yaml
license: Apache-2.0                          # SPDX id of the license we redistribute under
metadata:
  provenance: derived                        # derived | original | unknown (absent = unknown)
  upstream: owner/repo@<sha>:<path>          # the compared upstream revision and skill path
  upstream-license: Apache-2.0               # the license that applies upstream (skill LICENSE.txt > repo LICENSE)
  changes: "one line on what changed here"   # quote it: a bare value must not contain ': '
```

Keep the upstream `LICENSE*` file in the skill directory (Apache-2.0 and MIT
both require it) and never edit it. Every bundled file that differs from the
upstream revision carries a modification notice on its first line
(`<!-- Modified from owner/repo@sha:path; ... -->`, or a `#` comment in
scripts), which is what Apache-2.0 section 4(b) asks for. If the origin is not
known, write `upstream: unknown` and say so in `changes`; never guess an
author. A skill you wrote yourself gets `provenance: original` once that is
confirmed; without the key it is listed as "origin not yet confirmed".
`just skills-readme-index` turns this into the README credits block, and
`just skills-audit` rejects a derived skill whose contract is incomplete.

## Comparing a fork with its upstream (the dedup playbook)

The trigger is a skill of ours and an installed third-party skill that answer
the same request (a routing dry-run names one as a close runner-up of the
other). "Newest upstream" is not automatically better: our forks have been
de-crufted on purpose.

1. **Fetch, do not install.** `git clone --depth 1` the upstream into a scratch
   directory. Never run `bunx skills check` or `update` before comparing: they
   rewrite the store copy of anything the CLI tracks, including forks it once
   installed.
2. **Quantitative pass.** `just skills-compare skills/<fork> <scratch>/<upstream-skill>`
   for size, description length, tooling violations, and diff size.
3. **Independent judge.** Give a read-only model both files with the prompt
   below (capability inventory first, scores with quoted evidence, one of
   four verdicts). Verify every quoted line against the files before acting on
   a finding.
4. **Decide**: `KEEP_FORK` / `PORT_UPSTREAM_INTO_FORK` /
   `REPLACE_FORK_WITH_UPSTREAM` / `KEEP_BOTH_DIFFERENTIATE` (only the fork's
   description is edited in the last case — an edit to an installed skill is
   lost on reinstall).
5. **Execute in this order: place the successor → verify every consumer can
   read it → retire the old copy.**
   - keep/port: edit the fork, PR, merge, rsync to the homes,
     `bunx skills remove -g <upstream-name> -y` (the default scope is the
     project, `-g` is mandatory; the CLI links into every agent directory it
     knows, so removal reaches them all), `just dump-skills-lock`.
   - replace: place the upstream for each consumer first
     (`CLAUDE_CONFIG_DIR=~/.claude-work-x bunx skills add <repo> -g -s <name> -y -a claude-code`
     per Claude profile; a relative symlink `~/.codex/skills/<name> ->
     ../../.agents/skills/<name>` where the CLI links nothing), then delete the
     fork in a PR and remove its copies from the homes.
   - afterwards: `just skills-audit-consumers`, remove any dangling symlink
     the CLI left behind, and confirm with pi (below).
6. **Confirm routing** with a fresh pi session (a session that already
   discussed the removed skill keeps naming it):
   `pi -p --tools read --no-session --model opencode-go/glm-5.3 "<routing prompt>" < /dev/null`.
   pi's own view of the installed skills, without a model call:
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

Run it before and after the change with the same requests; a same-purpose
runner-up that disappears is the evidence.

## Rewriting a skill in another language

Instructions are English; the Japanese-writing skills and anything printed or
filled in for a person (templates, assets, Slack messages, report formats,
setup notices, quoted trigger phrases) stay in the reader's language. After a
rewrite, run a fidelity check with a read-only model: original vs rewrite,
report only semantic differences (omission, addition, meaning change,
reference break) with both quotes and a severity, verdict FAITHFUL or
NEEDS_FIX. Revert every medium or high finding before merging.

## Before making the submodule public

Run `gitleaks git` and `trufflehog git --only-verified` over the full history,
grep the tree and history for mention IDs, emails, internal hostnames, org
names, and personal profiles, and reconcile every derived skill's license
obligations (LICENSE file kept, changes stated). Report; do not change the
visibility.
