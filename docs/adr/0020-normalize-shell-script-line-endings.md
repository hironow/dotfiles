# 0020. Normalize shell-script line endings via `.gitattributes`

**Date:** 2026-06-02
**Status:** Accepted

## Context

PR #128 (ADR 0018, Windows native MVP) and PR #131 (ADR 0019, Windows scoop
manifest dump) both hit the same wall on the maintainer's Windows native
host:

- The prek `just lint` hook (which runs
  `git ls-files -z '*.sh' | xargs -r mise x -- shellcheck`) and the pytest
  case `test_install_sh_passes_shellcheck` failed with
  `SC1017 "Literal carriage return"` on every shell script in the repo.
- Root cause: git's `core.autocrlf=true` (the Windows default, also true on
  this host) converts the working tree to CRLF on every checkout.
  shellcheck reads the working tree, so it sees CR characters and flags
  them as errors.
- The Linux CI runner has `core.autocrlf=false` (or equivalent), so its
  working tree is LF and shellcheck passes. CI is green; only local Windows
  is broken.

Both PRs bypassed the hook with `--no-verify` and labelled the issue
"Windows shellcheck environment is a separate task". This ADR closes that
loop.

A `git ls-files --eol '*.sh'` audit confirms the relevant facts:

- All 27 `.sh` files report `i/lf w/crlf attr/` — the **index** is already
  LF (the blob stored by git is LF); only the working tree differs because
  of autocrlf.
- Zero files are `i/crlf`. There is no file whose blob contents would
  change if line endings were normalized — only the operator's working
  tree changes.

This means the fix is purely declarative: tell git that `*.sh` is LF, and
the autocrlf default no longer matters.

## Decision

Add to `.gitattributes`:

```gitattributes
*.sh   text eol=lf
*.bash text eol=lf
```

The `dump/scoop.json text eol=lf` rule introduced by ADR 0019 stays —
it's a specific-file rule for a non-shell artifact (JSON), conceptually
distinct from a wildcard rule for shell sources.

After the rule is committed, a one-shot `git add --renormalize .` updates
every operator's working tree to LF on the next pull, without changing
blob content (because all blobs are already LF).

**Scope is deliberately narrow:**

- Only `.sh` and `.bash`. `.zsh` / `.bats` do not exist in the repo today;
  adding them is future-proof but not required.
- Repo-wide `* text=auto` is NOT introduced. It would silently re-encode
  binary blobs that lack proper attribute coverage, and the blast radius
  exceeds what this ADR's failure justifies.
- Windows-native scripts (`.bat`, `.cmd`, `.ps1`) are NOT covered. The
  repo has effectively none of these; if added later, they should be
  pinned `text eol=crlf` (PowerShell tolerates LF but convention is CRLF)
  in a follow-up ADR.

## Enforcement inventory

- **`.gitattributes`**: 5 lines added (1 blank + 4 comment + 2 rules)
  alongside the existing ADR 0019 block.
- **Working tree renormalize**: `git add --renormalize .` is run once at
  ADR 0020 landing time. Expected to produce zero staged content diffs
  (the audit confirms `i/lf` everywhere); if any file *does* show up, it
  was an exceptional `i/crlf` blob and the diff is reviewed individually
  before commit.
- **Existing tests now pass hands-free on Windows**:
    - `tests/test_install_os_dispatch.py::test_install_sh_passes_shellcheck`
      no longer requires `--no-verify` (it already worked on CI; this just
      brings local Windows into parity).
    - `just lint` / `just check` (prek pre-push hook) work end-to-end on
      Windows. PRs from a Windows operator do not need `--no-verify`.
- **No new tests added**. The contract is enforced by git's own
  `.gitattributes` mechanism and the existing shellcheck guard; a test that
  asserts `.gitattributes` contains specific lines would be tautological
  given the single source of truth.

## Consequences

**Positive**

- Windows native operators can run `just lint` / `just check` / the full
  prek hook chain without `--no-verify`. The `--no-verify` escape hatch
  from PR #128 and PR #131 is no longer needed for shellcheck reasons
  (other reasons may still apply in isolation).
- Behaviour is reproducible across operator git configurations:
  contributors with `core.autocrlf=true`, `false`, or `input` all get
  the same working tree.
- The "Windows shellcheck environment" line item from the recent ADR
  follow-up list is closed.

**Negative**

- Win operators who previously edited a `.sh` in a CRLF-only editor
  (notepad.exe) will see git convert it to LF on save / commit. Modern
  editors (VS Code, Notepad++, etc.) already honour `.gitattributes`,
  so this is mostly theoretical.
- Anyone running `git status` for the first time after pulling this ADR
  may see "no changes" but their working tree silently flipped from CRLF
  to LF. This is the intended behaviour; documented here for transparency.

**Neutral**

- `dump/scoop.json text eol=lf` (ADR 0019) is now superficially redundant
  with the wildcard rule on `*.sh`, but is kept verbatim: JSON is not a
  shell script, and the specific-file rule documents its own ADR origin.
  Removing it would create a cross-ADR coupling for a one-line save.
- The `*.bash` rule covers zero files at landing time. It is future-proof
  insurance for the next shell script someone wants to commit with an
  explicit `.bash` extension.
