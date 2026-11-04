// Package harnesses holds the harness definitions as data: for each harness,
// a directory with its harness.json, the JSON Schema of each event's payload
// (with the "x-ir" map of fields to IR), and fixtures with their expected IR.
// The binary embeds them, so it reads nothing from the checkout at run time.
package harnesses

import "embed"

// FS holds one directory per harness, named for it.
//
//go:embed agy claude codex
var FS embed.FS
