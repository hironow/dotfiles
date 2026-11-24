# Plan and code review

Read this before you show the human a plan that changes behavior: code,
config, dependencies, infrastructure, or the rules in these instructions. A
plan that only fixes typos, comments, or formatting needs no review.
Someone independent must review the plan **before** the human sees it. Never
skip this review. CLAUDE.md has the pointer here. The same rules apply when
you ask for a review of code (a diff or a pull request).

## Review against the requirements

A reviewer told to "review critically" finds something every round, and an
author who adopts every finding lets the review, not the requirement, set the
scope. Every word of the prompt tilts the answer, so:

- **Brief the reviewer with the requirements.** Put in the prompt the human's
  request (quoted), what "done" means, and the rules that apply (file paths).
  The reviewer judges the plan or the code against them, not against its own
  preferences.
- **Ask a neutral question with an empty answer allowed.** Ask for two kinds
  of finding only: a requirement or rule the work breaks, quoted; or a bug,
  with the situation and the wrong result. Say that "no findings" is a
  complete answer, and often the right one. Do not ask it to "find" problems
  or improvements.
- **Accept a finding only when** it shows a bug or a broken requirement or
  rule, and you confirmed it (the lenses below). Decline everything else
  (preference, style, a refactor, scope beyond the request) and write the
  reason in one line. Declining every finding is a valid outcome.
- **At most three rounds.** Round 1 reviews the whole. Rounds 2 and 3 review
  only what changed and whether the accepted findings are fixed. After round
  3, settle what is left with a test, or record it as an open risk in the
  pull request. No fourth round, for any finding.
- **What a test or a measurement can settle, settle by a test**, instead of
  another round (docs/agents/performance.md: a suggestion is a hypothesis
  until a comparison supports it).
- **When two requirements conflict** in a finding, you decide which one wins
  for this work, and record the decision and the reason in the plan or the
  pull request. Do not send the conflict back for another round.
- **When you pass findings to an author** (a subagent, or yourself in a new
  step), ask it to evaluate each one: accept the ones that fix a bug or a
  broken requirement, and decline the rest with a reason. Say that declining
  all of them is fine.
- **When you ask anyone to improve your own work** (find optimizations,
  refactor, tidy), name the requirement it serves, and leave "no change is
  needed" open as an answer.

## The three lenses (use them for the whole review)

- **何も信用しない — trust nothing.** Treat every claim as a hypothesis to
  check: the reviewer's, the plan's, and your own. Do not act on a finding
  until you confirm it against the actual code, the docs, or a live experiment.
- **The reviewers get reviewed too.** The reviewer can be wrong (old
  knowledge, missing repo context). Judge each finding on its evidence, and
  push back when it is wrong. Your rebuttal must meet the same bar you set for
  the reviewer.
- **Fix the process that made the code, not just the code.** When a finding is
  real, prefer the change that stops the whole class of problem from coming
  back (the rule, template, or check that caused it) over patching one
  instance.

## Primary path: Codex

```sh
# ~/.codex/config.toml chooses the model. Never pin -m here: a pinned model id
# stops working when Codex retires that model, and then every review fails.

# Round 1: the whole plan or diff:
codex exec --skip-git-repo-check \
  "{plan_or_diff_full_path} を、次の要件に照らしてレビューして: {要件: 依頼の引用、完了の条件、関係する規則のファイルパス}。報告するのは 2 種類だけ: (a) 破っている要件または規則 (引用して)、(b) 実際に起きる不具合 (状況と、何がどう悪くなるか)。好みや改善の提案は挙げない。どちらも無ければ「指摘なし」とだけ答えてよい。それは正しい答えであることが多い。just check・just ci・just test のような全体の gate は実行しない。確かめるなら、指摘に関わるテストとチェックだけを最小で回して。ファイルは変更しない。"

# Rounds 2 and 3 (`resume --last` keeps the earlier context):
codex exec resume --skip-git-repo-check --last \
  "更新しました。採った指摘が直っているかと、変えた部分だけを、同じ要件で見て: (a) 破っている要件・規則 (引用して)、(b) 実際に起きる不具合。無ければ「指摘なし」とだけ答えてよい。just check・just ci・just test のような全体の gate は実行しない。ファイルは変更しない。"
```

The reviewer model's knowledge can be out of date. To correct for that,
collect current docs and URLs into a temp file and pass its path in the
prompt.

A reviewer never runs the whole gate. Do not let it run `just check`,
`just ci`, `just test`, or any other command that runs all of CI at once: the
gate is slow, and in the reviewer's sandbox it can fail for reasons that say
nothing about the change. A reviewer may run the smallest test or check that
covers a finding, such as one test file or a lint of one changed file. Say so
in every prompt, as the commands above do. Write the command names in the
prompt without backticks: inside the double quotes the shell would run them.
You run the full gate yourself.

## Fallback: independent subagent (when Codex is unavailable)

Codex is unavailable when it hits a rate limit (for example "You've hit your
usage limit…") or any hard error. Then review the plan in a **separate context
window**. Never review it inline in the context that wrote it: that removes the
independence the review is for.

1. Spawn a fresh subagent with the Agent tool (`general-purpose`, or `Plan`
   for a read-only review). A fresh spawn does not remember writing the plan,
   which is the point. Do not use a fork of the conversation that wrote the
   plan.
2. Put these in its prompt: the plan's full path, the requirements (as above),
   the three lenses, the same two kinds of finding and the "no findings" answer
   you give Codex, and the limit on what it may run.
3. Treat its findings exactly like Codex's: confirm each one, accept only a bug
   or a broken requirement, and keep the three-round limit.

## After the review

- Record which findings you accepted or declined, with the reason or what
  confirmed each, in the plan file itself or in the pull request description.
- docs/handover.md holds session state; it is not a review log. Record a risk
  there only if it is still unresolved (the same line the GRIT rules draw).
