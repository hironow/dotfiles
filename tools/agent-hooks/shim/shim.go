// Package shim holds the shim protocol: how a shim, an extension that runs
// inside a harness (Pi), asks the agent-hook binary about one hook call, and
// how the binary answers. Each version is a pair of JSON Schemas, embedded
// in the binary: v1/request.schema.json (the shim's request on stdin) and
// v1/response.schema.json (the binary's answer on stdout).
package shim

import _ "embed"

// RequestV1 is the JSON Schema of a version 1 request.
//
//go:embed v1/request.schema.json
var RequestV1 []byte

// ResponseV1 is the JSON Schema of a version 1 response.
//
//go:embed v1/response.schema.json
var ResponseV1 []byte
