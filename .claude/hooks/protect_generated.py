"""Stop edits to the generated documents (docs/generated/). A Claude Code PreToolUse hook.

Only `just generate` writes the generated documents. This hook refuses Edit / Write calls on them
and shell commands that rewrite them. Exit code 2 stops the tool call and returns the message to Claude.
The real guarantee is `just generated-check`; this hook only stops the mistake earlier.
"""

import json
import re
import sys

GENERATED = "docs/generated"
# A redirect counts only when its target is the generated directory. The other commands count
# when the directory appears among their arguments.
WRITE_TO_GENERATED = re.compile(
    r">>?\s*[\"']?[^\s\"'|;&]*"
    + GENERATED
    + r"|(?:^|[|;&]\s*|\bxargs\s+)(?:tee|sed\s+-i|rm|mv|cp|truncate|chmod)\b[^|;&\n]*"
    + GENERATED,
    re.MULTILINE,
)
SLASHES = re.compile(r"[\\/]+")


def with_forward_slashes(text: str) -> str:
    """Windows paths use backslashes, escaped or not (`C:\\repo\\docs\\generated`). Compare in one form."""
    return SLASHES.sub("/", text)


MESSAGE = (
    f"{GENERATED}/ holds generated documents and is never edited by hand. "
    "To change their content, edit Glossary/*.lean and run `just generate`."
)


def main():
    # Claude Code sends UTF-8; sys.stdin would decode with the locale's encoding.
    call = json.loads(sys.stdin.buffer.read())
    tool = call.get("tool_name", "")
    args = call.get("tool_input", {})
    if tool in ("Edit", "Write", "NotebookEdit"):
        path = with_forward_slashes(
            str(args.get("file_path") or args.get("notebook_path") or "")
        )
        if f"/{GENERATED}/" in path or path.startswith(f"{GENERATED}/"):
            print(MESSAGE, file=sys.stderr)
            return 2
    if tool == "Bash" and WRITE_TO_GENERATED.search(
        with_forward_slashes(str(args.get("command", "")))
    ):
        print(MESSAGE, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
