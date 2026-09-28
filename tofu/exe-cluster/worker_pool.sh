# shellcheck shell=bash
#
# Shell functions the WorkerPool guard (atespace.tf) shares with the steps that
# take the pool's workers away. tofu embeds this file at the top of each
# script, so every caller runs the same check. Callers set KUBECONFIG and
# AX_HOME, and put ATESPACE and POOL in the environment.

# An actor is awake exactly while its task is Running, and taking its worker
# away CRASHES it (see the WorkerPool comment in atespace.tf). Fails the whole
# script, naming how many, when any task in the atespace is Running; a check
# that cannot list the tasks fails it too.
#   $1  who is checking; it prefixes each line
#   $2  what would crash the tasks: the first sentence of the refusal
refuse_while_tasks_run() {
  local running
  running="$(ax get tasks -a "$ATESPACE" | awk 'NR > 1 && $3 == "Running"' | wc -l | tr -d ' ')"
  if [ "$running" != "0" ]; then
    echo "$1: $running task(s) Running in atespace $ATESPACE." >&2
    echo "$2 Suspend every task (ax suspend task <name>) and apply again." >&2
    exit 1
  fi
  echo "$1: no task Running in atespace $ATESPACE"
}

# A worker reports its capacity once, at startup, to the store the API server
# has then (Substrate's internal/ateomcapacity). ate-controller registers the
# workers again in a store that replaced it, but no capacity report follows,
# so nothing is placed on them until they restart: after the store moved to
# pd-standard, tasks saw "no free workers" for over ten minutes. Restarts the
# pool's workers that started before the store's claim was created, and only
# while no task is Running. It deletes their pods rather than rolling the
# Deployment: a rollout's 4Gi surge pod cannot fit on the one node, so it
# would never finish. Needs STORE_NAMESPACE and STORE_CLAIM as well.
#   $1  who is restarting; it prefixes each line
restart_workers_from_a_replaced_store() {
  local born stale
  born="$(kubectl -n "$STORE_NAMESPACE" get pvc "$STORE_CLAIM" -o jsonpath='{.metadata.creationTimestamp}')"
  if [ -z "$born" ]; then
    echo "$1: the store's claim $STORE_NAMESPACE/$STORE_CLAIM has no creation time" >&2
    exit 1
  fi
  # Start times and the claim's creation time are both RFC 3339 UTC, so they
  # compare as strings. A pod that has not started yet has none and will
  # report to this store.
  stale="$(kubectl -n "$ATESPACE" get pods -l "ate.dev/worker-pool=$POOL" \
      -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.startTime}{"\n"}{end}' |
    awk -v born="$born" '$2 != "" && $2 < born { print $1 }')"
  if [ -z "$stale" ]; then
    echo "$1: every $POOL worker started on the current store"
    return 0
  fi
  refuse_while_tasks_run "$1" "Restarting $POOL's workers onto the replaced store would CRASH them."
  echo "$1: restarting the $POOL workers that predate the store: $(echo "$stale" | tr '\n' ' ')"
  printf '%s\n' "$stale" | xargs kubectl -n "$ATESPACE" delete pod --wait=true --timeout=10m
  kubectl -n "$ATESPACE" wait --for=condition=Ready pod -l "ate.dev/worker-pool=$POOL" --timeout=10m
  echo "$1: $POOL's workers are up on the current store"
}
