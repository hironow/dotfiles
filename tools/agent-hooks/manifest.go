// Package agenthooks holds the data the agent-hook binary embeds besides the
// harness definitions (in package harnesses): the manifest of its hooks.
package agenthooks

import _ "embed"

// Manifest is manifest.json: each hook's id, the event it runs on (pre or
// post), and its failure mode. A "closed" hook (the guards) blocks a call
// whose input it cannot read; an "open" hook (rtk, the formatter) lets it
// go on and does nothing, as the old scripts failed open. The kinds and the
// order a registration needs come with the renderer (PR 3 of
// docs/plan/agent-hooks-go.md).
//
//go:embed manifest.json
var Manifest []byte
