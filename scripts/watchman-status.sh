#!/usr/bin/env bash
# Watchman status helper
# - Idempotent: read-only inspection
# - Behavior:
#   * If `watchman` CLI exists: prints get-pid and watch-list (pretty with jq if available)
#   * If CLI missing: prints `skip-watchman` and best-effort hints
#       - Processes: `hint-proc: ...`
#       - Sockets:   `hint-sock: ...`
#       - If a socket is found, query JSON-RPC ["get-pid"], ["watch-list"] via python when available

set -euo pipefail

echo "== Watchman ステータスの確認 =="

print_with_cli() {
  echo "Watchman CLI を検出しました。PID と監視ルートを取得します。"
  if command -v jq >/dev/null 2>&1; then
    echo "PID(JSON):"
    watchman get-pid | jq '.'
    echo "監視ルート(JSON):"
    watchman watch-list | jq '.'
  else
    echo "PID(JSON raw):"
    watchman get-pid
    echo "監視ルート(JSON raw):"
    watchman watch-list
  fi
}

query_socket_python() {
  # $1: socket path
  local sock="$1"
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$sock" <<'PY' || true
import socket, json, sys
sock_path = sys.argv[1]

def query(cmd):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(sock_path)
        s.sendall((json.dumps(cmd) + "\n").encode())
        data = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break
        line = data.decode(errors="ignore").splitlines()[0] if data else "{}"
        obj = json.loads(line)
        print(json.dumps(obj, ensure_ascii=False))
    except Exception as e:
        print(f"hint-error: {e}")

query(["get-pid"])
query(["watch-list"])
PY
  elif command -v python >/dev/null 2>&1; then
    python - "$sock" <<'PY' || true
import socket, json, sys
sock_path = sys.argv[1]

def query(cmd):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(sock_path)
        s.sendall((json.dumps(cmd) + "\n").encode())
        data = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break
        line = data.decode(errors="ignore").splitlines()[0] if data else "{}"
        obj = json.loads(line)
        print(json.dumps(obj, ensure_ascii=False))
    except Exception as e:
        print("hint-error: {}".format(e))

query(["get-pid"])
query(["watch-list"])
PY
  fi
}

probe_without_cli() {
  echo 'skip-watchman'
  echo 'Watchman CLI が見つかりません。バックグラウンドのデーモンが稼働していないか確認します。'

  # プロセス候補
  echo 'プロセス候補:'
  pgrep -fl watchman 2>/dev/null | sed 's/^/  • /' || true

  # ソケット候補: 代表的な場所を走査
  echo 'ソケット候補:'
  [ -S "$HOME/.watchman/sock" ] && echo "  • $HOME/.watchman/sock"
  if [ -n "${TMPDIR:-}" ] && [ -S "$TMPDIR/watchman-$USER/state/sock" ]; then
    echo "  • $TMPDIR/watchman-$USER/state/sock"
  fi
  local d
  for d in /opt/homebrew/var/run/watchman /usr/local/var/run/watchman /var/run/watchman; do
    [ -d "$d" ] || continue
    find "$d" -maxdepth 3 -type s -name sock 2>/dev/null | sed 's/^/  • /'
  done

  # Try querying the first available socket
  local sock=""
  if [ -S "$HOME/.watchman/sock" ]; then
    sock="$HOME/.watchman/sock"
  elif [ -n "${TMPDIR:-}" ] && [ -S "$TMPDIR/watchman-$USER/state/sock" ]; then
    sock="$TMPDIR/watchman-$USER/state/sock"
  else
    for d in /opt/homebrew/var/run/watchman /usr/local/var/run/watchman /var/run/watchman; do
      [ -d "$d" ] || continue
      first=$(find "$d" -maxdepth 3 -type s -name sock 2>/dev/null | head -n1)
      if [ -n "$first" ]; then sock="$first"; break; fi
    done
  fi

  if [ -n "$sock" ]; then
    echo "ソケットに直接問い合わせを試みます: $sock"
    query_socket_python "$sock"
    echo '注: 直接問い合わせはベストエフォートです。失敗しても異常ではありません。'
  fi

  echo '次のアクション候補:'
  echo '  1) brew install watchman で CLI を導入'
  echo '  2) 既存の古いユーザーソケット(~/.watchman/sock など)を削除して再起動'
  echo '  3) Homebrew サービスを使う場合は brew services restart watchman'
}

main() {
  # No arguments at present, keep for future options
  case "${1:-}" in
    -*|--*) ;; # ignore unknowns for now
  esac

  if command -v watchman >/dev/null 2>&1; then
    print_with_cli
  else
    probe_without_cli
  fi
}

main "$@"
