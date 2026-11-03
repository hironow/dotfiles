# Harness definitions

One directory per harness. The binary embeds them (`harnesses.go`), so a field that moves upstream is a change here, not in Go.

- `harness.json`:
    - the versions the definition was written for;
    - the harness's tool names, each mapped to a kind (`shell`, `write`, `edit`, `notebook`, `patch`);
    - per event, the payload's schema and the answer to each outcome.
- An answer has an exit code and `stdout`, `stderr`, or `stdoutJSON`.
    - Each text is a Go `text/template`. In `stdoutJSON`, every string is one, and the value is written as compact JSON and a newline.
    - A template reads `.Reason` (why the hook blocked), `.Rule`, and `.Message` (the reason after `BLOCKED:` and a space, as the old guards wrote it).
    - `oneLine` makes a text one line, as `guard-codex.sh` does for Codex.
- `pre.schema.json`: the JSON Schema of the native pre payload.
    - `x-ir` maps each IR field to its candidate JSON Pointers. The first candidate that is present and not `null` or `false` is taken, as jq's `//` takes it.
    - `x-ir-undeclared` lists the pointers the schema does not declare: fields the old guards read for every harness, though this one never sends them.
- `fixtures/`: payloads, each with its expected IR (`<name>.ir.json`).

Where the fixtures come from:

- `claude/`: captured from Claude Code 2.1.316, with ids and paths replaced by placeholders. The schema is written from the hooks reference and these payloads.
- `codex/`: constructed from Codex's generated schema (`codex-rs/hooks/schema/generated/pre-tool-use.command.input.schema.json` at `rust-v0.166.0`), from which `pre.schema.json` is derived. Live captures replace them when Codex is wired (PR 3 of `docs/plan/agent-hooks-go.md`).
