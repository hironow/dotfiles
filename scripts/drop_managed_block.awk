# Remove one dotfiles-managed block from a file on stdin, keeping every other line.
# Usage: awk -v b='<begin marker>' -v e='<end marker>' -f drop_managed_block.awk < profile
# The block is written with one blank line before it, so one blank line goes with it;
# refreshing (drop, then append) therefore never piles up blank lines.
$0 == b { skip = 1; if (pending > 0) pending--; next }
skip { if ($0 == e) skip = 0; next }
/^$/ { pending++; next }
{ while (pending > 0) { print ""; pending-- } print }
END { while (pending > 0) { print ""; pending-- } }
