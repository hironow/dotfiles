# The `mise activate` managed block of a PowerShell profile (ADR 0024, ADR 0086).
# Usage: PS_MISE_BLOCK="<current block>" awk -v mode=state|upgrade -f mise_block.awk profile
#   state:   prints absent, unclosed, current or stale
#   upgrade: prints the profile with the block replaced by the current one, in
#            place, every other line kept; exits 3 when the block is absent or
#            unclosed (the caller then leaves the file alone)
# The block is the begin marker up to the next end marker. It is unclosed when
# no end marker follows before the end of the file or before another managed
# block's begin marker: the end marker is shared between blocks, so taking the
# next one would swallow that block and the user's lines before it. Markers are
# compared without a trailing CR, and a CRLF block is written back with CRLF.
BEGIN {
  b = "# >>> dotfiles managed block: mise activate >>>"
  e = "# <<< end dotfiles managed block <<<"
  any = "# >>> dotfiles managed block:"
  n = split(ENVIRON["PS_MISE_BLOCK"], want, "\n")
  state = 0  # 0 before the block, 1 inside it, 2 after it
}
{ raw = $0; line = raw; cr = sub(/\r$/, "", line) }
state == 0 && line == b {
  state = 1; got = 1; body[got] = line
  if (mode == "upgrade") { eol = cr ? "\r" : ""; for (i = 1; i <= n; i++) printf "%s%s\n", want[i], eol }
  next
}
state == 1 {
  if (index(line, any) == 1) { unclosed = 1; state = 2 }
  else { got++; body[got] = line; if (line == e) state = 2 }
  if (mode == "upgrade" && unclosed) print raw
  next
}
mode == "upgrade" { print raw }
END {
  if (state == 0) result = "absent"
  else if (state == 1 || unclosed) result = "unclosed"
  else {
    same = (got == n)
    for (i = 1; same && i <= n; i++) if (body[i] != want[i]) same = 0
    result = same ? "current" : "stale"
  }
  if (mode == "state") print result
  else if (result == "absent" || result == "unclosed") exit 3
}
