# Remove one dotfiles-managed block from a file on stdin, keeping every other line.
# Usage: awk -v b='<begin marker>' -v e='<end marker>' -f drop_managed_block.awk < profile
# The block is written with one blank line before it, so one blank line goes with it;
# refreshing (drop, then append) therefore never piles up blank lines.
# Markers are compared without a trailing CR, so a profile an editor saved with
# CRLF still matches (a missed marker would re-append a duplicate block).
{ line = $0; sub(/\r$/, "", line) }
line == b { skip = 1; if (pending > 0) pending--; next }
skip { if (line == e) skip = 0; next }
line == "" { pending++; next }
{ while (pending > 0) { print ""; pending-- } print }
END { while (pending > 0) { print ""; pending-- } }
