---
name: block-rm-rf
enabled: true
event: bash
pattern: rm\s+-rf\s+/
action: block
---

# Dangerous rm Command Blocked

This hook prevents accidental execution of `rm -rf /` or similar dangerous commands that could delete critical system files.

## Why This Hook Exists

- `rm -rf /` can destroy your entire filesystem
- `rm -rf /*` can delete all files in the root directory
- Even with sudo protection, these commands are extremely dangerous

## What To Do

1. Double-check the path you intended to delete
2. Use more specific paths instead of root-level deletions
3. Consider using `trash` command for safer file removal
4. If you really need to delete something in `/`, do it manually and carefully
