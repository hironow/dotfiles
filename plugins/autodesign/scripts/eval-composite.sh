#!/usr/bin/env bash
# eval-composite.sh - Orchestrator for autodesign evaluators
#
# Reads design-config.yaml, runs enabled evaluators, checks constraints,
# and outputs composite_score.
#
# Usage: bash eval-composite.sh [config-path]
# Default config: design-config.yaml in current directory

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${1:-design-config.yaml}"

if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: Config not found: $CONFIG" >&2
  exit 1
fi

# Parse YAML using yq if available, otherwise grep/sed fallback
parse_yaml() {
  local key="$1"
  if command -v yq &>/dev/null; then
    yq -r "$key" "$CONFIG" 2>/dev/null || echo ""
  else
    # Simple grep/sed fallback for flat keys
    grep -E "^\s*${key}:" "$CONFIG" 2>/dev/null | sed 's/.*:\s*//' | tr -d '"' || echo ""
  fi
}

# Get eval_target
EVAL_TARGET=$(parse_yaml '.eval_target')
if [[ -z "$EVAL_TARGET" ]]; then
  echo "ERROR: eval_target not found in config" >&2
  exit 1
fi

# Initialize scores
declare -A scores
declare -A weights
total_weight=0
constraint_violated="none"

# Check if evaluator is enabled (yq or grep fallback)
is_enabled() {
  local evaluator="$1"
  if command -v yq &>/dev/null; then
    local enabled
    enabled=$(yq -r ".evaluators.${evaluator}.enabled // false" "$CONFIG" 2>/dev/null)
    [[ "$enabled" == "true" ]]
  else
    grep -A2 "^\s*${evaluator}:" "$CONFIG" | grep -q "enabled:\s*true"
  fi
}

get_weight() {
  local evaluator="$1"
  if command -v yq &>/dev/null; then
    yq -r ".evaluators.${evaluator}.weight // 0" "$CONFIG" 2>/dev/null
  else
    grep -A3 "^\s*${evaluator}:" "$CONFIG" | grep "weight:" | sed 's/.*weight:\s*//' | tr -d ' '
  fi
}

get_constraint() {
  local key="$1"
  if command -v yq &>/dev/null; then
    yq -r ".constraints.${key} // \"\"" "$CONFIG" 2>/dev/null
  else
    grep "^\s*${key}:" "$CONFIG" | sed 's/.*:\s*//' | tr -d ' '
  fi
}

# Run evaluators
run_evaluator() {
  local name="$1"
  local script="${SCRIPT_DIR}/evaluators/${name}.sh"

  if [[ ! -f "$script" ]]; then
    echo "WARNING: Evaluator script not found: $script" >&2
    return 1
  fi

  bash "$script" "$EVAL_TARGET" 2>/dev/null
}

# Structure evaluator
if is_enabled "structure"; then
  w=$(get_weight "structure")
  weights[structure]="$w"
  total_weight=$(echo "$total_weight + $w" | bc -l)

  output=$(run_evaluator "structure" || echo "structure_errors: 999")
  structure_errors=$(echo "$output" | grep "^structure_errors:" | awk '{print $2}')
  structure_score=$(echo "$output" | grep "^structure_score:" | awk '{print $2}')
  scores[structure]="${structure_score:-0}"

  echo "structure_errors: ${structure_errors:-999}"
  echo "structure_score: ${structure_score:-0}"

  # Check constraint
  max_errors=$(get_constraint "structure_errors_max")
  if [[ -n "$max_errors" && -n "$structure_errors" ]]; then
    if (( structure_errors > max_errors )); then
      constraint_violated="structure_errors_max"
    fi
  fi
fi

# Readability evaluator
if is_enabled "readability"; then
  w=$(get_weight "readability")
  weights[readability]="$w"
  total_weight=$(echo "$total_weight + $w" | bc -l)

  output=$(run_evaluator "readability" || echo "aeo_score: 0")
  aeo_score=$(echo "$output" | grep "^aeo_score:" | awk '{print $2}')
  scores[readability]="${aeo_score:-0}"

  echo "aeo_score: ${aeo_score:-0}"

  # Check constraint
  min_score=$(get_constraint "aeo_score_min")
  if [[ -n "$min_score" && -n "$aeo_score" && "$constraint_violated" == "none" ]]; then
    if (( $(echo "$aeo_score < $min_score" | bc -l) )); then
      constraint_violated="aeo_score_min"
    fi
  fi
fi

# Lighthouse evaluator
if is_enabled "lighthouse"; then
  w=$(get_weight "lighthouse")
  weights[lighthouse]="$w"
  total_weight=$(echo "$total_weight + $w" | bc -l)

  output=$(run_evaluator "lighthouse" || echo "lighthouse_avg: 0")
  lighthouse_avg=$(echo "$output" | grep "^lighthouse_avg:" | awk '{print $2}')
  scores[lighthouse]="${lighthouse_avg:-0}"

  echo "lighthouse_avg: ${lighthouse_avg:-0}"

  # Check constraint
  min_score=$(get_constraint "lighthouse_avg_min")
  if [[ -n "$min_score" && -n "$lighthouse_avg" && "$constraint_violated" == "none" ]]; then
    if (( $(echo "$lighthouse_avg < $min_score" | bc -l) )); then
      constraint_violated="lighthouse_avg_min"
    fi
  fi
fi

# Completeness evaluator
if is_enabled "completeness"; then
  w=$(get_weight "completeness")
  weights[completeness]="$w"
  total_weight=$(echo "$total_weight + $w" | bc -l)

  output=$(run_evaluator "completeness" || echo "completeness_score: 0")
  completeness_score=$(echo "$output" | grep "^completeness_score:" | awk '{print $2}')
  scores[completeness]="${completeness_score:-0}"

  echo "completeness_score: ${completeness_score:-0}"

  # Check constraint
  min_score=$(get_constraint "completeness_score_min")
  if [[ -n "$min_score" && -n "$completeness_score" && "$constraint_violated" == "none" ]]; then
    if (( $(echo "$completeness_score < $min_score" | bc -l) )); then
      constraint_violated="completeness_score_min"
    fi
  fi
fi

# Calculate composite score (normalize weights to sum to 1.0)
composite=0
if (( $(echo "$total_weight > 0" | bc -l) )); then
  for key in "${!scores[@]}"; do
    w="${weights[$key]:-0}"
    s="${scores[$key]:-0}"
    normalized_w=$(echo "$w / $total_weight" | bc -l)
    contribution=$(echo "$normalized_w * $s" | bc -l)
    composite=$(echo "$composite + $contribution" | bc -l)
  done
fi

composite=$(printf "%.2f" "$composite")

echo "constraint_violated: $constraint_violated"
echo "composite_score: $composite"
