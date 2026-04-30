# .semgrep/

Project-wide Semgrep rules. Organized by category.

## Layout

```
.semgrep/
  rules/
    meta/       # Self-consistency rules for rule files (ROOT_AGENTS.md etc.)
    {domain}/   # Project-specific rules (concurrency, api, persistence, ...)
  README.md
```

## Categories

### meta/

Rules that enforce the self-consistency of the rule files themselves
(ROOT_AGENTS.md, AGENTS.md, CLAUDE.md, .cursorrules). These rules prevent
the "the rule file violates its own rules" failure mode.

Currently enforces:

- **compose-v1-filename-must-be-sentineled** — Every literal occurrence of
  deprecated Compose v1 filenames (`docker-compose.yaml`, `docker-compose.yml`)
  in a rule file must be wrapped in `<prohibited-filename>...</prohibited-filename>`.

## Running

```bash
# Full scan (all categories)
semgrep --config .semgrep/rules/ --error .

# Meta only (fast; validates rule files)
semgrep --config .semgrep/rules/meta/ --error .

# Run the rule's own test cases
semgrep --test --config .semgrep/rules/meta/
```

## Adding a rule

1. Create `rules/{category}/{rule-id}.yaml`
   - One rule per file
   - Filename matches rule id
   - Rule id format: `{project-prefix | meta}-{category}-{short-name}`
2. Create companion test `rules/{category}/{rule-id}.test.{ext}`
   - Use `<!-- ruleid: ... -->` above lines that SHOULD match
   - Use `<!-- ok: ... -->` above lines that SHOULD NOT match
   - Pick an extension that the rule's `languages:` covers
3. Run `semgrep --test --config rules/{category}/` and verify green
4. Add to CI

## Distribution across projects

Place this `.semgrep/` directory at the repo root, per project.
If rules are shared across projects, reference a single source of truth:

**Option 1 — symlink from dotfiles (simplest)**

```bash
ln -s ~/dotfiles/.semgrep/rules/meta ~/work/myproject/.semgrep/rules/meta
```

**Option 2 — git subtree** (when you want per-project divergence history)

```bash
git subtree add --prefix .semgrep/rules/meta \
  git@github.com:hironow/dotfiles-semgrep.git main --squash
```

Meta rules are the natural candidate for sharing — domain rules usually stay
project-local.
