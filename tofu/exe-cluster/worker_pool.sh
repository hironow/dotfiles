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
