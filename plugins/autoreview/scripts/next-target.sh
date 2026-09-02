#!/usr/bin/env bash
# next-target.sh - Pick the next (category, file) for an autoreview iteration.
#
# Reads review-config.yaml (rule_categories, max_iterations_per_category,
# max_consecutive_no_improvement, results_file) and the review-results.tsv it
# names, then applies the loop-control rules deterministically so the agent
# does not have to count rows by hand.
#
# Output (stdout), exactly one tab-separated line:
#   <category>\t<file>\t<reason>   next target; <file> is "-" when no file of
#                                  that category has known remaining findings
#                                  (scan target_paths to pick one)
#   DONE\t<reason>                 nothing left to work on
#
# Categories newly retired by a cap are reported on stderr as
#   skip: <category>: <reason>
# so the caller can append a "skip" row to review-results.tsv.
#
# Usage: next-target.sh [review-config.yaml] [review-results.tsv]
#
# review-results.tsv schema (header row, tab-separated):
#   commit mode category file findings_before findings_after status description
#
# Ordering: categories by most remaining findings first; within the chosen
# category, the file with the most remaining findings.
#
# Assumptions, stated because the TSV does not carry them:
# - "iterations" counts keep/revert/crash rows; a "skip" row marks a category
#   as already retired and excludes it from selection.
# - findings_after is per (category, file) - that is what the reviewer scans -
#   so remaining findings are tracked per (category, file): the latest row for
#   that pair wins, and a category's remaining count is their sum.
# - A category whose logged files are all clean is NOT retired: unscanned files
#   under target_paths may still have findings, so it is offered again with
#   file "-" (ranked below any category with known findings). Termination then
#   comes from the reviewer logging a "skip" row when a rescan finds nothing,
#   or from max_iterations_per_category / max_consecutive_no_improvement.
# - rule_categories: [] (empty) means "all categories", resolved from the
#   guardrails rules directory via resolve-guardrails.sh (its "tests" directory
#   holds rule fixtures, not a category); if that fails, the categories already
#   present in the TSV are used.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${1:-review-config.yaml}"

if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: config not found: $CONFIG" >&2
  exit 1
fi

scalar() {
  # scalar <key> <default>
  local value
  value=$(sed -n "s/^$1:[[:space:]]*//p" "$CONFIG" | head -1)
  value="${value%%#*}"
  value="$(printf '%s' "$value" | tr -d "\"' " )"
  [[ -n "$value" ]] && printf '%s' "$value" || printf '%s' "$2"
}

MAX_ITER=$(scalar max_iterations_per_category 5)
MAX_STALL=$(scalar max_consecutive_no_improvement 2)
RESULTS="${2:-$(scalar results_file review-results.tsv)}"

read_categories() {
  awk -v q="'" '
    /^rule_categories:/ {
      line = $0
      sub(/^rule_categories:[[:space:]]*/, "", line)
      sub(/[[:space:]]*#.*$/, "", line)
      if (line ~ /^\[.*\]$/) {
        gsub(/^\[|\]$/, "", line)
        gsub(/"/, "", line); gsub(q, "", line)
        n = split(line, a, /,/)
        for (i = 1; i <= n; i++) {
          gsub(/^[ \t]+|[ \t]+$/, "", a[i])
          if (a[i] != "") print a[i]
        }
        exit
      }
      inblock = 1
      next
    }
    inblock && /^[[:space:]]+-[[:space:]]*/ {
      v = $0
      sub(/^[[:space:]]+-[[:space:]]*/, "", v)
      sub(/[[:space:]]*#.*$/, "", v)
      gsub(/"/, "", v); gsub(q, "", v)
      gsub(/^[ \t]+|[ \t]+$/, "", v)
      if (v != "") print v
      next
    }
    inblock && /^[^[:space:]]/ { exit }
  ' "$CONFIG"
}

CATEGORIES=$(read_categories)

if [[ -z "$CATEGORIES" ]]; then
  if RULES_DIR=$(bash "$SCRIPT_DIR/resolve-guardrails.sh" 2>/dev/null); then
    CATEGORIES=$(find "$RULES_DIR" -mindepth 1 -maxdepth 1 -type d \
      ! -name tests -exec basename {} \; | sort)
  elif [[ -f "$RESULTS" ]]; then
    CATEGORIES=$(awk -F'\t' 'NR > 1 && NF >= 7 { print $3 }' "$RESULTS" | sort -u)
  fi
fi

if [[ -z "$CATEGORIES" ]]; then
  printf 'DONE\tno rule_categories configured and no rules directory to derive them from\n'
  exit 0
fi

# Per-category summary from the results file, one tab-separated row of:
#   <category> <iterations> <consecutive_no_improvement> <remaining>
#   <best_file> <retired> <oscillating> <files_logged>
# remaining is the sum of the latest findings_after over the category's files;
# best_file is the file holding the most of them, or "-" when none is known.
summarize() {
  [[ -f "$RESULTS" ]] || return 0
  awk -F'\t' -v OFS='\t' '
    NR == 1 && $1 == "commit" { next }
    NF < 7 { next }
    {
      cat = $3
      seen[cat] = 1
      if ($7 == "skip") { retired[cat] = 1; next }
      iters[cat]++
      f = ($4 == "" ? "-" : $4)
      key = cat SUBSEP f
      if (!(key in known)) {
        known[key] = 1
        nfiles[cat]++
        order[cat, nfiles[cat]] = f
      }
      rem[key] = $6 + 0
      if ($7 == "keep") { stall[cat] = 0 } else { stall[cat]++ }
      s3[cat] = s2[cat]; s2[cat] = s1[cat]; s1[cat] = $7
    }
    END {
      for (c in seen) {
        osc = 0
        if (iters[c] >= 3 &&
            ((s1[c] == "keep" && s2[c] == "revert" && s3[c] == "keep") ||
             (s1[c] == "revert" && s2[c] == "keep" && s3[c] == "revert"))) osc = 1
        total = 0
        best = "-"
        best_rem = 0
        for (i = 1; i <= nfiles[c] + 0; i++) {
          f = order[c, i]
          total += rem[c, f]
          if (rem[c, f] > best_rem) { best_rem = rem[c, f]; best = f }
        }
        print c, iters[c] + 0, stall[c] + 0, total, best, retired[c] + 0, osc, \
              nfiles[c] + 0
      }
    }
  ' "$RESULTS"
}

SUMMARY=$(summarize)

field() {
  # field <category> <1-based column in SUMMARY> <default>
  local row
  row=$(printf '%s\n' "$SUMMARY" | awk -F'\t' -v c="$1" '$1 == c { print; exit }')
  [[ -n "$row" ]] && printf '%s' "$(printf '%s' "$row" | cut -f"$2")" || printf '%s' "$3"
}

best_cat=""
best_file=""
best_reason=""
best_tier=-1
best_rank=-1

while IFS= read -r cat; do
  [[ -n "$cat" ]] || continue
  iters=$(field "$cat" 2 0)
  stall=$(field "$cat" 3 0)
  remaining=$(field "$cat" 4 0)
  file=$(field "$cat" 5 -)
  retired=$(field "$cat" 6 0)
  osc=$(field "$cat" 7 0)
  logged=$(field "$cat" 8 0)

  if [[ "$retired" == "1" ]]; then
    continue
  fi
  # Oscillation first: it is the most specific reason, and it needs three
  # iterations, which is often max_iterations_per_category itself.
  if [[ "$osc" == "1" ]]; then
    echo "skip: $cat: keep/revert oscillation in the last 3 iterations" >&2
    continue
  fi
  if ((stall >= MAX_STALL)); then
    echo "skip: $cat: $stall consecutive iterations without improvement (max_consecutive_no_improvement=$MAX_STALL)" >&2
    continue
  fi
  if ((iters >= MAX_ITER)); then
    echo "skip: $cat: reached max_iterations_per_category ($MAX_ITER)" >&2
    continue
  fi

  # Tier 2: never scanned, baseline unknown. Tier 1: known findings left.
  # Tier 0: every logged file is clean, but target_paths may hold unvisited ones.
  if ((logged == 0)); then
    tier=2
    rank=0
    file="-"
    reason="no iteration logged yet; scan to establish the baseline"
  elif ((remaining > 0)); then
    tier=1
    rank=$remaining
    reason="$remaining findings remaining after $iters iteration(s)"
  else
    tier=0
    rank=0
    file="-"
    reason="every logged file is clean; scan target_paths for a file not visited yet"
  fi

  if ((tier > best_tier)) || { ((tier == best_tier)) && ((rank > best_rank)); }; then
    best_tier=$tier
    best_rank=$rank
    best_cat=$cat
    best_file=$file
    best_reason=$reason
  fi
done <<EOF
$CATEGORIES
EOF

if [[ -z "$best_cat" ]]; then
  printf 'DONE\tall categories are capped or skipped\n'
  exit 0
fi

printf '%s\t%s\t%s\n' "$best_cat" "$best_file" "$best_reason"
