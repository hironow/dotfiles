# shellcheck shell=bash
# ax-lib.sh: what ax-job and ax-exec share (Phase 6 plan D12). Sourced, never
# run; the wrapper sets AX_TOOL first.
#
# The lease rule is exe-reaper's (`may-start`), not re-implemented here. The
# command runs detached in the task and is followed by short `ax ssh` polls
# (ax-job-guest.sh), so a transport failure is only ever a failed poll, never
# the command's end.

AX_ATESPACE="${AX_ATESPACE:-exe}"
# How often to poll, how long a task may take to be Running, how many polls
# in a row may fail before the task counts as unreachable, and how long one
# `ax ssh` call may take.
AX_JOB_POLL_SECONDS="${AX_JOB_POLL_SECONDS:-5}"
AX_JOB_START_SECONDS="${AX_JOB_START_SECONDS:-600}"
AX_JOB_MAX_POLL_FAILURES="${AX_JOB_MAX_POLL_FAILURES:-12}"
AX_JOB_SSH_SECONDS="${AX_JOB_SSH_SECONDS:-60}"

# The wrappers' own exit codes, besides the command's.
readonly EXIT_REFUSED=3      # the lease said not now
readonly EXIT_UNREACHABLE=69 # the task stopped answering; the command may still run
readonly EXIT_SUSPENDED=75   # the task was suspended (a drain) or lost /tmp mid-command
readonly EXIT_TIMEOUT=124    # --timeout ran out, and the command's process group was killed

AX_GUEST="$(cat "$(dirname "${BASH_SOURCE[0]}")/ax-job-guest.sh")"

log() { printf '[%s] %s\n' "$AX_TOOL" "$*" >&2; }
die() {
	log "$*"
	exit 1
}
usage_error() {
	log "$*"
	exit 2
}

command -v timeout >/dev/null || die "timeout(1) is required (coreutils)"

# seconds DURATION: 90s, 30m or 2h, in seconds.
seconds() {
	[[ "$1" =~ ^([0-9]+)([smh])$ ]] || return 1
	local n="${BASH_REMATCH[1]}"
	case "${BASH_REMATCH[2]}" in
	s) echo "$n" ;;
	m) echo $((n * 60)) ;;
	h) echo $((n * 3600)) ;;
	esac
}

# may_start SECONDS: may a task start now, with the lease running at least
# that long? exe-reaper says why not on stderr.
may_start() {
	local rc=0
	exe-reaper may-start -need "${1}s" >/dev/null || rc=$?
	case "$rc" in
	0) return 0 ;;
	3) return "$EXIT_REFUSED" ;;
	*)
		log "exe-reaper may-start failed (exit $rc)"
		return 1
		;;
	esac
}

# task_phase NAME: the task's phase, or nothing if there is no such task.
# Fails if AX cannot be asked.
task_phase() {
	local listing
	listing="$(ax get tasks -a "$AX_ATESPACE")" || return 1
	awk -v n="$1" 'NR > 1 && $1 == n { print $3; exit }' <<<"$listing"
}

# wait_running NAME: until the task is Running, for AX_JOB_START_SECONDS.
wait_running() {
	local name="$1" phase deadline=$((SECONDS + AX_JOB_START_SECONDS))
	while :; do
		phase="$(task_phase "$name")" || phase="unknown"
		case "$phase" in
		Running) return 0 ;;
		Failed)
			log "task $name failed to start: ax describe task $name -a $AX_ATESPACE"
			return 1
			;;
		"")
			log "task $name is gone"
			return 1
			;;
		esac
		if ((SECONDS >= deadline)); then
			log "task $name was not Running within ${AX_JOB_START_SECONDS}s (it is $phase)"
			return 1
		fi
		sleep "$AX_JOB_POLL_SECONDS"
	done
}

# guest NAME OP ARGS...: one ax-job-guest.sh operation inside the task.
guest() {
	local name="$1"
	shift
	timeout "$AX_JOB_SSH_SECONDS" ax ssh "$name" -a "$AX_ATESPACE" -- sh -c "$AX_GUEST" ax-job-guest "$@"
}

# redact TEXT: TEXT with every Claude token masked: this run's own, and
# anything shaped like one Anthropic issues.
redact() {
	local s="$1"
	if [[ -n "${claude_token:-}" ]]; then
		s="${s//"$claude_token"/sk-ant-[REDACTED]}"
	fi
	printf '%s' "$s" | sed -E 's/sk-ant-[A-Za-z0-9_-]+/sk-ant-[REDACTED]/g'
}

# The command's output is printed a whole line at a time, so a token split
# across two polls is redacted like any other.
held=""
emit() {
	held+="$1"
	if [[ "$held" == *$'\n'* ]]; then
		redact "${held%$'\n'*}"$'\n'
		held="${held##*$'\n'}"
	fi
}
flush() {
	if [[ -n "$held" ]]; then
		redact "$held"$'\n'
		held=""
	fi
}

# run_detached NAME TIMEOUT_SECONDS CMD...: run CMD in task NAME and follow it
# to its end. Prints its output; returns its exit code, or EXIT_TIMEOUT,
# EXIT_SUSPENDED or EXIT_UNREACHABLE. Sets `ended` to 1 only when the command
# is certainly over: its exit code, a confirmed kill, or a task that failed
# or went away. With claude_token set, CMD runs under env
# CLAUDE_CODE_OAUTH_TOKEN, passed in the launch's argv and nowhere else.
ended=0
# shellcheck disable=SC2034 # ended is read by the wrapper that sources this file
run_detached() {
	local name="$1" timeout_s="$2"
	shift 2
	local -a cmd=("$@")
	if [[ -n "${claude_token:-}" ]]; then
		cmd=(env "CLAUDE_CODE_OAUTH_TOKEN=$claude_token" "$@")
	fi
	local id tag dir out="" attempt err
	id="$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
	tag="AXJOB-$(od -An -N8 -tx1 /dev/urandom | tr -d ' \n')"
	dir="/tmp/ax-job/$id"
	err="$(mktemp)"
	ended=0

	# A launch whose reply is lost may still have started CMD; sending it
	# again is safe, since the guest starts CMD only once per DIR.
	for attempt in 1 2 3; do
		if out="$(guest "$name" launch "$dir" "${cmd[@]}" 2>"$err")" && [[ "$out" == *started* ]]; then
			break
		fi
		out=""
		log "launch attempt $attempt failed: $(redact "$(tail -n 1 "$err")")"
		sleep "$AX_JOB_POLL_SECONDS"
	done
	if [[ "$out" != *started* ]]; then
		rm -f "$err"
		log "could not confirm the launch in task $name; it may be running: ax ssh $name -a $AX_ATESPACE -- cat $dir/log"
		return "$EXIT_UNREACHABLE"
	fi

	local offset=0 failures=0 since=$SECONDS size status phase
	held=""
	while :; do
		out="$(guest "$name" poll "$dir" "$offset" "$tag" 2>"$err")" || true
		if [[ "$out" == *$'\n'"$tag "* ]]; then
			failures=0
			emit "${out%$'\n'"$tag" *}"
			read -r size status <<<"${out##*$'\n'"$tag" }"
			offset="$size"
			case "$status" in
			running) ;;
			lost)
				flush
				rm -f "$err"
				log "task $name lost the command's state mid-command (suspended or restarted); the task is kept"
				return "$EXIT_SUSPENDED"
				;;
			*)
				flush
				rm -f "$err"
				if [[ ! "$status" =~ ^[0-9]+$ ]]; then
					log "task $name reported an unreadable exit status; the task is kept"
					return "$EXIT_UNREACHABLE"
				fi
				ended=1
				return "$status"
				;;
			esac
		else
			failures=$((failures + 1))
			phase="$(task_phase "$name")" || phase="unknown"
			case "$phase" in
			Suspended)
				flush
				rm -f "$err"
				log "task $name was suspended mid-command (a drain?); the task is kept: ax-exec $name resumes it"
				return "$EXIT_SUSPENDED"
				;;
			Failed | "")
				flush
				rm -f "$err"
				log "task $name ${phase:-is gone} mid-command"
				ended=1
				return 1
				;;
			esac
			if ((failures >= AX_JOB_MAX_POLL_FAILURES)); then
				flush
				log "task $name stopped answering ($failures polls in a row: $(redact "$(tail -n 1 "$err")"))"
				log "the command may still be running, so the task is kept: ax ssh $name -a $AX_ATESPACE -- cat $dir/exit; ax delete task $name -a $AX_ATESPACE"
				rm -f "$err"
				return "$EXIT_UNREACHABLE"
			fi
		fi
		if ((SECONDS - since >= timeout_s)); then
			flush
			rm -f "$err"
			for attempt in 1 2 3; do
				if out="$(guest "$name" kill "$dir" 2>/dev/null)" && [[ "$out" == *killed* ]]; then
					log "timed out after ${timeout_s}s; the command's process group was killed"
					ended=1
					return "$EXIT_TIMEOUT"
				fi
				sleep "$AX_JOB_POLL_SECONDS"
			done
			log "timed out after ${timeout_s}s, and the kill could not be confirmed; the task is kept"
			return "$EXIT_TIMEOUT"
		fi
		sleep "$AX_JOB_POLL_SECONDS"
	done
}

# read_claude_token: the Claude token (plan Q20), from Secret Manager on the
# operator's own credentials, into the shell variable claude_token: never
# exported, never written to a file.
claude_token=""
read_claude_token() {
	local err
	err="$(mktemp)"
	if ! claude_token="$(gcloud secrets versions access latest --secret="${EXE_CLAUDE_SECRET:?}" --project="${EXE_PROJECT_ID:?}" 2>"$err")"; then
		claude_token=""
		log "could not read the Claude token: $(tail -n 1 "$err")"
		rm -f "$err"
		return 1
	fi
	rm -f "$err"
	if [[ -z "$claude_token" ]]; then
		log "the Claude token in Secret Manager is empty"
		return 1
	fi
}
