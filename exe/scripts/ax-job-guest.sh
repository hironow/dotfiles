# shellcheck shell=sh
# ax-job-guest.sh: the half of ax-job and ax-exec that runs inside the task
# (Phase 6 plan D12). They pass this whole file to `sh -c` through `ax ssh`,
# one short call at a time:
#
#   launch DIR CMD...     start CMD once, detached, in its own session
#   poll DIR OFFSET TAG   CMD's output from byte OFFSET, then "\nTAG SIZE STATUS",
#                         STATUS being its exit code, "running", or "lost"
#   kill DIR              kill CMD's whole process group
#
# Never one long stream: in Phase 5 a silent `ax ssh` reset with RST_STREAM,
# and a reset stream does not stop the command it carried. So CMD runs
# detached, writes its exit code when it ends, and every call here returns at
# once. DIR is under /tmp, never /workspace, so no snapshot carries it: after
# a suspend it is gone, and poll says "lost".
#
# POSIX sh: the task image's /bin/sh is dash.

set -u
op=$1
dir=$2
shift 2

case $op in
launch)
	mkdir -p "${dir%/*}" || exit 1
	if ! mkdir "$dir" 2>/dev/null; then
		# A launch whose reply was lost, sent again: the first one started CMD.
		echo started
		exit 0
	fi
	# setsid makes CMD's shell a session and process-group leader, so kill
	# takes everything CMD starts. That shell writes its own pid, the group's
	# id, once it leads the group, and launch answers only then: before
	# setsid, CMD still shares this call's group, and a kill, or the end of
	# this `ax ssh` session, would miss it or take it along. The exit code
	# lands by rename, never half-written, and only after the output is whole.
	# shellcheck disable=SC2016 # expanded by the detached shell, not this one
	setsid sh -c 'd=$1; shift; echo $$ >"$d/pid.tmp"; mv "$d/pid.tmp" "$d/pid"; "$@" >"$d/log" 2>&1; echo $? >"$d/exit.tmp"; mv "$d/exit.tmp" "$d/exit"' \
		ax-job-run "$dir" "$@" </dev/null >/dev/null 2>&1 &
	i=0
	while [ ! -f "$dir/pid" ] && [ "$i" -lt 100 ]; do
		sleep 0.1
		i=$((i + 1))
	done
	if [ ! -f "$dir/pid" ]; then
		echo "ax-job-guest: the command did not start within 10s" >&2
		exit 1
	fi
	echo started
	;;
poll)
	offset=$1
	tag=$2
	status=running
	if [ ! -d "$dir" ]; then
		status=lost
	elif [ -f "$dir/exit" ]; then
		# Read before the size: once the exit code exists, the log is whole.
		status=$(cat "$dir/exit")
	fi
	size=0
	if [ -f "$dir/log" ]; then
		size=$(wc -c <"$dir/log")
		size=$((size + 0))
	fi
	if [ "$size" -gt "$offset" ]; then
		tail -c +"$((offset + 1))" "$dir/log" | head -c "$((size - offset))"
	fi
	printf '\n%s %s %s\n' "$tag" "$size" "$status"
	;;
kill)
	# No pid: nothing was started, so nothing is left to kill.
	pgid=$(cat "$dir/pid" 2>/dev/null) || {
		echo killed
		exit 0
	}
	kill -s TERM -- "-$pgid" 2>/dev/null
	i=0
	while kill -s 0 -- "-$pgid" 2>/dev/null && [ "$i" -lt 20 ]; do
		sleep 0.5
		i=$((i + 1))
	done
	kill -s KILL -- "-$pgid" 2>/dev/null
	echo killed
	;;
*)
	echo "ax-job-guest: unknown operation $op" >&2
	exit 2
	;;
esac
