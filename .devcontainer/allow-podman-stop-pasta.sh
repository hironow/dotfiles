#!/usr/bin/env bash
# Let rootless Podman stop pasta on Ubuntu 26.04 CI runners, and only when a
# probe proves it cannot.
#
# Ubuntu 26.04's passt package ships an enforced AppArmor profile "pasta"
# whose signal rules accept only unconfined senders, while podman runs under
# the "podman" label. Podman's SIGTERM to pasta, which tears down the rootless
# network namespace, is then denied, and removing the last container fails
# with "rootless netns: kill network process: permission denied" (Ubuntu
# LP #2154379, actions/runner-images #15182). The image fix
# (runner-images PR #15184) adds the rule below; this does the same on the
# throwaway runner when the image does not have it yet.
#
# Usage: allow-podman-stop-pasta.sh PROFILE (ci-bootstrap.sh passes
# /etc/apparmor.d/usr.bin.pasta). Exit 0: pasta teardown works (already, or
# after the rule). Anything else stops the bootstrap: a different cause is
# diagnosed, not patched.
set -euo pipefail

profile="${1:?usage: allow-podman-stop-pasta.sh PROFILE}"
rule='  signal (receive) set=(term) peer=podman,'

say() { printf 'pasta-guard: %s\n' "$*"; }

# The journal position now; denials are read only after it, so an older one
# never counts. A read that fails is never taken as "no denial".
journal_cursor() {
  local out cursor
  if ! out="$(sudo -n journalctl --no-pager -q -n 1 --show-cursor)"; then
    say "cannot read the journal (cursor)" >&2
    return 1
  fi
  cursor="$(printf '%s\n' "$out" | sed -n 's/^-- cursor: //p' | tail -n 1)"
  if [[ -z "$cursor" ]]; then
    say "the journal gave no cursor" >&2
    return 1
  fi
  printf '%s\n' "$cursor"
}

# journald stores a kernel or audit record a moment after the event; --sync
# waits until it has processed what is pending.
journal_sync() {
  if ! sudo -n journalctl --sync; then
    say "cannot sync the journal" >&2
    return 1
  fi
}

# Kernel and audit records after CURSOR (AppArmor denials arrive as either).
journal_after() {
  if ! sudo -n journalctl --no-pager -q --after-cursor="$1" _TRANSPORT=kernel _TRANSPORT=audit; then
    say "cannot read the journal after the cursor" >&2
    return 1
  fi
}

# The exact denial: pasta refusing to receive SIGTERM from podman.
has_pasta_denial() {
  local line
  while IFS= read -r line; do
    if [[ $line == *'apparmor="DENIED"'* && $line == *'operation="signal"'* &&
      $line == *'profile="pasta"'* && $line == *'signal=term'* &&
      $line == *'peer="podman"'* && $line =~ denied_mask=\"[^\"]*receive ]]; then
      return 0
    fi
  done <<< "$1"
  return 1
}

# Teardown works when the command succeeds and does not report the error
# (podman can print it and still exit 0).
probe() {
  local output rc=0
  output="$(podman unshare --rootless-netns true 2>&1)" || rc=$?
  say "probe: podman unshare --rootless-netns true exited $rc"
  [[ -z "$output" ]] || printf '%s\n' "$output"
  [[ $rc -eq 0 && ! ($output == *'rootless netns'* && $output == *'kill network process'*) ]]
}

# A rule in the profile itself (not a child profile) that lets it receive
# SIGTERM from podman: a signal rule, not deny, with receive access (or none
# given), a set with term (or none given), and the peer podman exactly.
has_rule() {
  local line access depth=0
  while IFS= read -r line; do
    line="${line%%#*}"
    if [[ $line =~ \{[[:space:]]*$ ]]; then
      depth=$((depth + 1))
      continue
    fi
    if [[ $line =~ ^[[:space:]]*\}[[:space:]]*$ ]]; then
      depth=$((depth - 1))
      continue
    fi
    [[ $depth -eq 1 ]] || continue
    [[ $line =~ ^[[:space:]]*(audit[[:space:]]+)?(allow[[:space:]]+)?signal([[:space:]]|,) ]] || continue
    [[ $line =~ peer=podman([[:space:]]|,|$) ]] || continue
    access=
    if [[ $line =~ signal[[:space:]]*\(([^\)]*)\) ]]; then
      access="${BASH_REMATCH[1]}"
    elif [[ $line =~ signal[[:space:]]+(receive|send|read|write|rw|r|w)([[:space:]]|,) ]]; then
      access="${BASH_REMATCH[1]}"
    fi
    if [[ -n $access && ! $access =~ (^|[[:space:],])(receive|read|rw|r)([[:space:],]|$) ]]; then
      continue
    fi
    if [[ $line =~ set=\(([^\)]*)\) ]]; then
      [[ ${BASH_REMATCH[1]} =~ (^|[[:space:],])term([[:space:],]|$) ]] || continue
    elif [[ $line =~ set=([[:alnum:]]+) ]]; then
      [[ ${BASH_REMATCH[1]} == term ]] || continue
    fi
    return 0
  done < "$profile"
  return 1
}

# Insert the rule before the profile's closing brace. Every other line stays
# as it was; a missing final newline is added.
add_rule() {
  local last edited
  last="$(awk 'NF { n = NR } END { print n + 0 }' "$profile")"
  if [[ $last -eq 0 || "$(sed -n "${last}p" "$profile" | tr -d '[:space:]')" != '}' ]]; then
    say "$profile does not end with the profile's closing brace; not editing it" >&2
    return 1
  fi
  edited="$(mktemp "${RUNNER_TEMP:?}/pasta-profile.XXXXXX")"
  awk -v rule="$rule" -v last="$last" 'NR == last { print rule } { print }' "$profile" > "$edited"
  sudo -n cp -- "$edited" "$profile"
  cmp -s -- "$edited" "$profile"
  rm -f -- "$edited"
  say "added to $profile: ${rule#  }"
}

if [[ -f $profile ]]; then
  say "$profile signal rules:"
  grep -n 'signal' "$profile" || say "(none)"
else
  say "$profile does not exist"
fi

cursor="$(journal_cursor)"
if probe; then
  say "pasta teardown works; not reproduced on this runner, nothing changed"
  exit 0
fi
# Look again for a few seconds before concluding there is no denial.
for attempt in 1 2 3 4 5; do
  journal_sync
  since="$(journal_after "$cursor")"
  if has_pasta_denial "$since"; then
    break
  fi
  if [[ $attempt -lt 5 ]]; then
    sleep 1
  fi
done
if ! has_pasta_denial "$since"; then
  say "the probe failed without pasta's SIGTERM denial; a different cause, not patched" >&2
  printf '%s\n' "$since" >&2
  exit 1
fi
say "the probe failed with pasta's SIGTERM denial"
if [[ ! -f $profile ]]; then
  say "but $profile does not exist; not patched" >&2
  exit 1
fi
if has_rule; then
  say "$profile already allows it; reloading it"
else
  add_rule
fi
sudo -n apparmor_parser -r "$profile"

cursor="$(journal_cursor)"
if ! probe; then
  say "the probe still fails after the rule" >&2
  exit 1
fi
journal_sync
since="$(journal_after "$cursor")"
if has_pasta_denial "$since"; then
  say "pasta's SIGTERM is still denied after the rule" >&2
  printf '%s\n' "$since" >&2
  exit 1
fi
say "pasta teardown fixed by the AppArmor rule"
