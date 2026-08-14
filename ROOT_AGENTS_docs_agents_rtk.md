# RTK — Rust Token Killer

Read this when running shell commands through `rtk`, checking its token
savings, or debugging output that looks unexpectedly filtered.

`rtk` is a token-optimized CLI proxy (cuts up to 90% of bash output). In
Claude Code a hook rewrites commands transparently (e.g. `git status` →
`rtk git status`); other agents invoke it explicitly.

## Meta commands (always call rtk directly)

```bash
rtk gain              # Show token savings analytics
rtk gain --history    # Show command usage history with savings
rtk discover          # Analyze command history for missed opportunities
rtk proxy <cmd>       # Execute raw command without filtering (for debugging)
```

## Installation verification

```bash
rtk --version         # Should show: rtk X.Y.Z
rtk gain              # Should work (not "command not found")
which rtk             # Verify correct binary
```

⚠️ **Name collision**: if `rtk gain` fails, you may have
reachingforthejack/rtk (Rust Type Kit) installed instead.
