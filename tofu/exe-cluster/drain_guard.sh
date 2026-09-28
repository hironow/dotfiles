# shellcheck shell=bash
#
# The drain check every exe-cluster step that could undo an L1 drain runs
# first: the Substrate install (substrate.tf) and the WorkerPool guard
# (atespace.tf). tofu embeds this file at the top of each check's script.
# Callers put OPS_BUCKET, exe-platform's ops bucket, in the environment.

# L1 closes the atenet-router and quiesces the ax-controller while it drains,
# and owns both replica counts until the drain is over (Phase 6 plan D2). The
# Substrate install re-applies the router's manifest, count included, so run
# mid-drain it reopens the path an auto-resume takes; and replacing the
# workers mid-drain crashes actors that are still checkpointing with every
# task already Suspended. Fails the whole script while drain.json in the ops
# bucket is in one of the named phases, and when it cannot be read: a step
# that cannot tell must not guess "no drain". No record at all is L1 never
# having ticked, which is no drain.
#   $1  who is checking; it prefixes each line
#   $2  the phases that block, space-separated (draining, drained)
refuse_while_draining() {
  local listing phase blocked
  if ! listing="$(gcloud storage ls "gs://$OPS_BUCKET/")"; then
    echo "$1: cannot list gs://$OPS_BUCKET to find drain.json" >&2
    exit 1
  fi
  if ! printf '%s\n' "$listing" | grep -qx "gs://$OPS_BUCKET/drain.json"; then
    echo "$1: no drain record yet, so no drain is in flight"
    return 0
  fi
  if ! phase="$(gcloud storage cat "gs://$OPS_BUCKET/drain.json" |
    python3 -c 'import json, sys; print(json.load(sys.stdin).get("phase", ""))')"; then
    echo "$1: drain.json cannot be read, so whether L1 is draining is unknown" >&2
    exit 1
  fi
  for blocked in $2; do
    if [ "$phase" = "$blocked" ]; then
      echo "$1: drain.json says $phase: L1 owns the router and the controller until the drain is over." >&2
      echo "Wait for the drain to end (just exe-status), or wake the node and let L1 cancel it, then apply again." >&2
      exit 1
    fi
  done
  echo "$1: drain.json says ${phase:-none}"
}
