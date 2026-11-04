# Harness definitions

One directory per harness. The binary embeds them (`harnesses.go`), so a field that moves upstream is a change here, not in Go.

- `harness.json`:
    - the versions the definition was written for;
    - the harness's tool names, each mapped to a kind (`shell`, `write`, `edit`, `notebook`, `patch`);
    - `pending`: tools the harness's docs name but no captured payload showed. They are not mapped, so no hook is registered for them.
    - `hookCwd`: where the harness runs its hooks.
        - `session`: in the session's directory (Claude, Codex).
        - `registration`: in the directory of the file that registers the hook (agy: its `hooks.json`). The formatter then runs its commands in the file's project instead, with the file's real path (`internal/project`).
    - `support`: each hook's level for each tool, by the hook's id in `manifest.json`.
        - `supported`: registered, and it does its whole job.
        - `degraded`: registered, with a known gap, given as the reason. The conformance suite (`internal/conformance`) pins the gap.
        - `unsupported`: not registered, for the reason given.
        - The tools a hook is registered for are today's matchers.
    - per event (`pre`, `post`), the payload's schema and the answer to each outcome: `pass`, `block`, and `forward` (a delegate's answer written as it is: rtk's, edited).
- An answer has an exit code and `stdout`, `stderr`, or `stdoutJSON`.
    - Each text is a Go `text/template`. In `stdoutJSON`, every string is one, and the value is written as compact JSON and a newline.
    - A template reads `.Reason` (why the hook blocked), `.Rule`, `.Message` (the reason after `BLOCKED:` and a space, as the old guards wrote it), `.Native` (a forwarded answer), and `.Notice` (what a pass reports, such as the formatter's).
    - `oneLine` makes a text one line, as `guard-codex.sh` does for Codex.
- `pre.schema.json` and `post.schema.json`: the JSON Schemas of the native payloads.
    - `x-ir-tool` is the JSON Pointer to the tool's name.
    - `x-ir` maps each IR field to its candidate JSON Pointers. The first candidate that is present and not `null` or `false` is taken, as jq's `//` takes it.
    - A pointer with one `*` token makes a list field. The `*` stands for every element of the array there; the pointer goes on inside each element. Each element is read as a single field is. A list pointer is its field's only candidate.
    - `x-ir-undeclared` lists the pointers the schema does not declare: fields the old guards read for every harness, though this one never sends them.
    - `x-success` (post only) says how the payload tells that the tool call succeeded:
        - `pointer`: the member that tells;
        - `values`: the strings, booleans, or `null` that mean success, compared after decoding;
        - `absent`: whether a missing member means success.
        - The member is read as written, so a number anywhere in the payload, however large, changes nothing.
        - After a call that failed, no post hook runs, and the binary answers the pass. A harness with none never reports a failure.
- `fixtures/`: payloads, each with its expected IR (`<name>.ir.json`).

Where the fixtures come from:

- `claude/`: captured from Claude Code 2.1.316 (PreToolUse: Bash, Write, Edit, NotebookEdit; PostToolUse: Write, Edit), with ids and paths replaced by placeholders. The schemas are written from the hooks reference and these payloads.
- `codex/`: constructed from Codex's generated schemas (`codex-rs/hooks/schema/generated/{pre,post}-tool-use.command.input.schema.json` at `rust-v0.166.0`), from which the schemas here are derived. Live captures replace them when Codex is wired (PR 3 of `docs/plan/agent-hooks-go.md`).
- `agy/`: captured from Antigravity CLI 1.5.0, through a project `.agents/hooks.json` in a scratch workspace with `agy -p --mode accept-edits`:
    - PreToolUse and PostToolUse of `run_command`, `write_file`, and `edit_file`;
    - an edit asked for two replacements, which came as one `edit_file` with multi-line `Target` and `Replacement`.
    - Ids, paths, and the prompt are replaced by placeholders. The schemas are written from agy's hooks docs and these payloads.
