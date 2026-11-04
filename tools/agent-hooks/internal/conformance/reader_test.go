package conformance

import (
	"fmt"
	"slices"
	"strings"
	"testing"

	"github.com/goccy/go-json/jsontext"
	json "github.com/goccy/go-json/v2"
)

// The readers below say what each harness makes of an answer. They are
// written from docs/plan/agent-hooks-go-contracts.md and Codex's source, not
// from the binary's answer templates, so a wrong template shows as a wrong
// verdict. Each is at least as strict as its harness: an answer the harness
// would act on in a way the binary never means is invalid.

// answer is what the binary wrote and how it exited.
type answer struct {
	exit           int
	stdout, stderr string
}

// The kinds of verdict.
const (
	pass    = "pass"
	block   = "block"
	rewrite = "rewrite"
	invalid = "invalid"
)

// verdict is what a harness does with an answer: its kind, a block's reason
// as the model sees it ("" for a block without one), a pass's notice, and
// why an answer is invalid.
type verdict struct {
	kind   string
	reason string
	notice string
	why    string
}

func passed(notice string) verdict      { return verdict{kind: pass, notice: notice} }
func blocked(reason string) verdict     { return verdict{kind: block, reason: reason} }
func invalidBecause(why string) verdict { return verdict{kind: invalid, why: why} }

// readers holds each harness's reader for each event.
var readers = map[string]map[string]func(answer) verdict{
	"claude": {"pre": readClaudePre, "post": readClaudePost},
	"codex":  {"pre": readCodexPre, "post": readCodexPost},
	"agy":    {"pre": readAgyPre, "post": readAgyPost},
}

// object reads text as one JSON object: its members, by name. Duplicate
// names, trailing text, and invalid UTF-8 are errors.
func object(text string) (map[string]jsontext.Value, error) {
	var members map[string]jsontext.Value
	if err := json.Unmarshal([]byte(text), &members); err != nil {
		return nil, err
	}
	if members == nil {
		return nil, fmt.Errorf("%q is not an object", text)
	}
	return members, nil
}

// stringMember returns a member that is a string; present is false for an
// absent or null member, and ok is false for one of another type.
func stringMember(members map[string]jsontext.Value, name string) (text string, present, ok bool) {
	value, found := members[name]
	if !found || value.Kind() == 'n' {
		return "", false, true
	}
	if value.Kind() != '"' {
		return "", true, false
	}
	return mustString(value), true, true
}

func mustString(value jsontext.Value) string {
	var text string
	if err := json.Unmarshal(value, &text); err != nil {
		panic(err)
	}
	return text
}

// Claude Code: exit 2 blocks, the stderr reaching the model; exit 0 applies
// the stdout's JSON, if any. The binary answers a pass with exit 0 and
// nothing on stdout.
func readClaudePre(a answer) verdict {
	switch a.exit {
	case 2:
		if reason := strings.TrimSpace(a.stderr); reason != "" {
			return blocked(reason)
		}
		return invalidBecause("exit 2 with no reason on stderr")
	case 0:
	default:
		return invalidBecause(fmt.Sprintf("exit %d", a.exit))
	}
	trimmed := strings.TrimSpace(a.stdout)
	if trimmed == "" {
		return passed(a.stderr)
	}
	top, err := object(trimmed)
	if err != nil {
		return invalidBecause("stdout is not one JSON object")
	}
	specific, err := object(string(top["hookSpecificOutput"]))
	if err != nil {
		return invalidBecause("JSON with no hookSpecificOutput")
	}
	event, _, _ := stringMember(specific, "hookEventName")
	decision, _, _ := stringMember(specific, "permissionDecision")
	reason, _, _ := stringMember(specific, "permissionDecisionReason")
	if event == "PreToolUse" && decision == "deny" && strings.TrimSpace(reason) != "" {
		return blocked(strings.TrimSpace(reason))
	}
	return invalidBecause("JSON the binary never writes for Claude")
}

// Claude Code's PostToolUse: the binary exits 0, its notice on stderr.
func readClaudePost(a answer) verdict {
	if a.exit != 0 || strings.TrimSpace(a.stdout) != "" {
		return invalidBecause(fmt.Sprintf("exit %d with stdout %q", a.exit, a.stdout))
	}
	return passed(a.stderr)
}

// codexPreEvent is the hookEventName a pre answer names. Codex's
// HookEventNameWire takes any event's name; the reader takes only this one.
const codexPreEvent = "PreToolUse"

// readCodexPre ports Codex's pre-tool-use handling at rust-v0.166.0
// (hooks/src/events/pre_tool_use.rs 219-291; engine/output_parser.rs
// parse_pre_tool_use and its checks; schema.rs's wire types, which deny
// unknown fields). Anything Codex finds invalid fails open, so it is invalid
// here.
func readCodexPre(a answer) verdict {
	switch a.exit {
	case 0:
	case 2:
		if reason := strings.TrimSpace(a.stderr); reason != "" {
			return blocked(reason)
		}
		return invalidBecause("exit 2 without a reason on stderr")
	default:
		return invalidBecause(fmt.Sprintf("exit %d fails open", a.exit))
	}
	trimmed := strings.TrimSpace(a.stdout)
	if trimmed == "" {
		return passed(a.stderr)
	}
	top, err := object(trimmed)
	if err != nil {
		return invalidBecause("stdout is not one JSON object")
	}
	if why := codexUniversal(top); why != "" {
		return invalidBecause(why)
	}
	// decision is an enum: when present (not null), only its two values
	// deserialize; "" is not one of them.
	legacyDecision, legacyDecisionPresent, ok := stringMember(top, "decision")
	if !ok || (legacyDecisionPresent && !slices.Contains([]string{"approve", "block"}, legacyDecision)) {
		return invalidBecause("decision is not approve or block")
	}
	legacyReason, legacyReasonPresent, ok := stringMember(top, "reason")
	if !ok {
		return invalidBecause("reason is not a string")
	}
	var specific map[string]jsontext.Value
	if value, found := top["hookSpecificOutput"]; found && value.Kind() != 'n' {
		if specific, err = object(string(value)); err != nil {
			return invalidBecause("hookSpecificOutput is not an object")
		}
		if why := codexSpecific(specific); why != "" {
			return invalidBecause(why)
		}
	}
	if decided, ok := codexSpecificDecision(specific); ok {
		return decided
	}
	switch {
	case legacyDecision == "approve":
		return invalidBecause("decision:approve")
	case legacyDecision == "block" && strings.TrimSpace(legacyReason) == "":
		return invalidBecause("decision:block without a non-empty reason")
	case legacyDecision == "block":
		return blocked(strings.TrimSpace(legacyReason))
	case legacyReasonPresent:
		return invalidBecause("reason without decision")
	default:
		return passed(a.stderr)
	}
}

// codexSpecificDecision is parse_pre_tool_use's hook-specific branch: when
// hookSpecificOutput holds a decision, a reason, or updatedInput, it alone
// decides (ok); otherwise the legacy top-level decision does.
func codexSpecificDecision(specific map[string]jsontext.Value) (verdict, bool) {
	decision, decisionPresent, _ := stringMember(specific, "permissionDecision")
	reason, reasonPresent, _ := stringMember(specific, "permissionDecisionReason")
	updated, updatedPresent := specific["updatedInput"]
	updatedPresent = updatedPresent && updated.Kind() != 'n'
	if !decisionPresent && !reasonPresent && !updatedPresent {
		return verdict{}, false
	}
	switch {
	case updatedPresent && decision != "allow":
		return invalidBecause("updatedInput without permissionDecision:allow"), true
	case decision == "allow" && !updatedPresent:
		return invalidBecause("permissionDecision:allow without updatedInput"), true
	case decision == "allow":
		return verdict{kind: rewrite}, true
	case decision == "ask":
		return invalidBecause("permissionDecision:ask"), true
	case decision == "deny" && strings.TrimSpace(reason) == "":
		return invalidBecause("deny without a non-empty reason"), true
	case decision == "deny":
		return blocked(strings.TrimSpace(reason)), true
	default:
		return invalidBecause("permissionDecisionReason without permissionDecision"), true
	}
}

// codexUniversal checks the top level's members (no unknown one, each of its
// wire type) and the universal fields PreToolUse does not support.
func codexUniversal(top map[string]jsontext.Value) string {
	for name, value := range top {
		switch name {
		case "continue", "suppressOutput":
			if value.Kind() != 't' && value.Kind() != 'f' {
				return name + " is not a boolean"
			}
		case "stopReason", "systemMessage", "reason", "decision":
			if value.Kind() != '"' && value.Kind() != 'n' {
				return name + " is not a string"
			}
		case "hookSpecificOutput":
		default:
			return "unknown member " + name
		}
	}
	if value, found := top["continue"]; found && value.Kind() == 'f' {
		return "continue:false"
	}
	if _, present, _ := stringMember(top, "stopReason"); present {
		return "stopReason"
	}
	if value, found := top["suppressOutput"]; found && value.Kind() == 't' {
		return "suppressOutput:true"
	}
	return ""
}

// codexSpecific checks hookSpecificOutput's members: no unknown one, each of
// its wire type, and hookEventName PreToolUse.
func codexSpecific(specific map[string]jsontext.Value) string {
	for name, value := range specific {
		switch name {
		case "hookEventName":
			if value.Kind() != '"' {
				return name + " is not a string"
			}
		case "permissionDecisionReason", "additionalContext":
			if value.Kind() != '"' && value.Kind() != 'n' {
				return name + " is not a string"
			}
		case "permissionDecision":
			if value.Kind() == 'n' {
				continue
			}
			if value.Kind() != '"' || !slices.Contains([]string{"allow", "deny", "ask"}, mustString(value)) {
				return "permissionDecision is not allow, deny, or ask"
			}
		case "updatedInput":
		default:
			return "unknown member hookSpecificOutput." + name
		}
	}
	if event, _, _ := stringMember(specific, "hookEventName"); event != codexPreEvent {
		return "hookEventName is not " + codexPreEvent
	}
	return ""
}

// Codex's post: the binary exits 0 with nothing on stdout, its notice on
// stderr.
func readCodexPost(a answer) verdict {
	if a.exit != 0 || strings.TrimSpace(a.stdout) != "" {
		return invalidBecause(fmt.Sprintf("exit %d with stdout %q", a.exit, a.stdout))
	}
	return passed(a.stderr)
}

// agy (probes 2026-11-03, 1.4.12; the contracts file): {"decision":"ask"}
// is as no hook; {"decision":"deny","reason":...} blocks with the reason as
// it is; {} denies with no reason; any non-zero exit blocks with agy's own
// error text. Undocumented answers are invalid.
func readAgyPre(a answer) verdict {
	if a.exit != 0 {
		return blocked("")
	}
	members, err := object(strings.TrimSpace(a.stdout))
	if err != nil {
		return invalidBecause("stdout is not one JSON object")
	}
	if len(members) == 0 {
		return blocked("")
	}
	for name := range members {
		if name != "decision" && name != "reason" {
			return invalidBecause("unknown member " + name)
		}
	}
	decision, _, _ := stringMember(members, "decision")
	reason, reasonPresent, reasonOK := stringMember(members, "reason")
	switch {
	case decision == "ask" && !reasonPresent:
		return passed(a.stderr)
	case decision == "deny" && reasonOK:
		return blocked(reason)
	default:
		return invalidBecause(fmt.Sprintf("decision %q", decision))
	}
}

// agy's post: the binary answers {}, its notice on stderr.
func readAgyPost(a answer) verdict {
	if a.exit != 0 {
		return invalidBecause(fmt.Sprintf("exit %d", a.exit))
	}
	if members, err := object(strings.TrimSpace(a.stdout)); err != nil || len(members) != 0 {
		return invalidBecause(fmt.Sprintf("stdout %q is not {}", a.stdout))
	}
	return passed(a.stderr)
}

func TestTheReadersReadEachHarnessAsItReadsItself(t *testing.T) {
	deny := func(reason string) string {
		return `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":` +
			reason + `}}`
	}
	tests := []struct {
		harness, event string
		answer         answer
		want           verdict
	}{
		// Claude.
		{"claude", "pre", answer{exit: 2, stderr: "BLOCKED: x\n"}, blocked("BLOCKED: x")},
		{"claude", "pre", answer{exit: 2}, invalidBecause("exit 2 with no reason on stderr")},
		{"claude", "pre", answer{exit: 2, stderr: " \n\t"}, invalidBecause("exit 2 with no reason on stderr")},
		{"claude", "pre", answer{exit: 1, stderr: "BLOCKED: x"}, invalidBecause("exit 1")},
		{"claude", "pre", answer{}, passed("")},
		{"claude", "pre", answer{stdout: deny(`"r"`)}, blocked("r")},
		{"claude", "pre", answer{stdout: deny(`""`)}, invalidBecause("JSON the binary never writes for Claude")},
		{"claude", "pre", answer{stdout: `{"x":`}, invalidBecause("stdout is not one JSON object")},
		{"claude", "post", answer{stderr: "n"}, passed("n")},
		{"claude", "post", answer{exit: 2, stderr: "n"}, invalidBecause(`exit 2 with stdout ""`)},
		// Codex: exit 2.
		{"codex", "pre", answer{exit: 2, stderr: " r \n"}, blocked("r")},
		{"codex", "pre", answer{exit: 2}, invalidBecause("exit 2 without a reason on stderr")},
		{"codex", "pre", answer{exit: 1, stdout: deny(`"r"`)}, invalidBecause("exit 1 fails open")},
		// Codex: the hook-specific decision.
		{"codex", "pre", answer{stdout: deny(`"r"`) + "\n"}, blocked("r")},
		{"codex", "pre", answer{stdout: deny(`"  "`)}, invalidBecause("deny without a non-empty reason")},
		{"codex", "pre", answer{stdout: deny(`null`)}, invalidBecause("deny without a non-empty reason")},
		{
			"codex", "pre",
			answer{stdout: `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny"}}`},
			invalidBecause("deny without a non-empty reason"),
		},
		{"codex", "pre", answer{stdout: `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny",` +
			`"permissionDecisionReason":"r","updatedInput":{}}}`}, invalidBecause("updatedInput without permissionDecision:allow")},
		{
			"codex", "pre",
			answer{stdout: `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecisionReason":"r"}}`},
			invalidBecause("permissionDecisionReason without permissionDecision"),
		},
		{
			"codex", "pre",
			answer{stdout: `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask"}}`},
			invalidBecause("permissionDecision:ask"),
		},
		{
			"codex", "pre",
			answer{stdout: `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}`},
			invalidBecause("permissionDecision:allow without updatedInput"),
		},
		{"codex", "pre", answer{stdout: `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow",` +
			`"updatedInput":{"command":"x"}}}`}, verdict{kind: rewrite}},
		{"codex", "pre", answer{stdout: `{"hookSpecificOutput":{"hookEventName":"PostToolUse","permissionDecision":"deny",` +
			`"permissionDecisionReason":"r"}}`}, invalidBecause("hookEventName is not PreToolUse")},
		{"codex", "pre", answer{stdout: `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny",` +
			`"permissionDecisionReason":"r","extra":1}}`}, invalidBecause("unknown member hookSpecificOutput.extra")},
		// Codex: the universal fields and the legacy decision.
		{"codex", "pre", answer{stdout: `{"extra":1}`}, invalidBecause("unknown member extra")},
		{"codex", "pre", answer{stdout: `{"continue":false}`}, invalidBecause("continue:false")},
		{"codex", "pre", answer{stdout: `{"continue":null}`}, invalidBecause("continue is not a boolean")},
		{"codex", "pre", answer{stdout: `{"stopReason":"s"}`}, invalidBecause("stopReason")},
		{"codex", "pre", answer{stdout: `{"suppressOutput":true}`}, invalidBecause("suppressOutput:true")},
		// decision is an enum (approve, block): "" does not deserialize, so
		// Codex fails open, even with a valid hook-specific deny; null is none.
		{"codex", "pre", answer{stdout: `{"decision":"","hookSpecificOutput":{"hookEventName":"PreToolUse",` +
			`"permissionDecision":"deny","permissionDecisionReason":"BLOCKED: x"}}`}, invalidBecause("decision is not approve or block")},
		{"codex", "pre", answer{stdout: `{"decision":"","reason":"r"}`}, invalidBecause("decision is not approve or block")},
		{"codex", "pre", answer{stdout: `{"decision":null,"hookSpecificOutput":{"hookEventName":"PreToolUse",` +
			`"permissionDecision":"deny","permissionDecisionReason":"BLOCKED: x"}}`}, blocked("BLOCKED: x")},
		{"codex", "pre", answer{stdout: `{"decision":"block","reason":"r"}`}, blocked("r")},
		{"codex", "pre", answer{stdout: `{"decision":"block"}`}, invalidBecause("decision:block without a non-empty reason")},
		{"codex", "pre", answer{stdout: `{"decision":"approve"}`}, invalidBecause("decision:approve")},
		{"codex", "pre", answer{stdout: `{"reason":"r"}`}, invalidBecause("reason without decision")},
		{"codex", "pre", answer{stdout: `{}`}, passed("")},
		{"codex", "pre", answer{stdout: `{"x":`}, invalidBecause("stdout is not one JSON object")},
		{
			"codex", "pre",
			answer{stdout: `{"decision":"block","reason":"a","reason":"b"}`},
			invalidBecause("stdout is not one JSON object"),
		},
		{"codex", "post", answer{stderr: "n"}, passed("n")},
		{"codex", "post", answer{stdout: "{}"}, invalidBecause(`exit 0 with stdout "{}"`)},
		// agy.
		{"agy", "pre", answer{stdout: `{"decision":"ask"}` + "\n"}, passed("")},
		{"agy", "pre", answer{stdout: `{"decision":"deny","reason":"BLOCKED: x"}`}, blocked("BLOCKED: x")},
		{"agy", "pre", answer{stdout: `{"decision":"deny"}`}, blocked("")},
		{"agy", "pre", answer{stdout: `{}`}, blocked("")},
		{"agy", "pre", answer{exit: 1, stdout: `{"decision":"ask"}`}, blocked("")},
		{"agy", "pre", answer{stdout: `{"decision":"allow"}`}, invalidBecause(`decision "allow"`)},
		{"agy", "pre", answer{stdout: ``}, invalidBecause("stdout is not one JSON object")},
		{"agy", "pre", answer{stdout: `{"decision":"ask"`}, invalidBecause("stdout is not one JSON object")},
		{"agy", "pre", answer{stdout: `{"decision":"ask","overwrite":{}}`}, invalidBecause("unknown member overwrite")},
		{"agy", "post", answer{stdout: "{}\n", stderr: "n"}, passed("n")},
		{"agy", "post", answer{stdout: `{"decision":"ask"}`}, invalidBecause(`stdout "{\"decision\":\"ask\"}" is not {}`)},
		{"agy", "post", answer{exit: 1, stdout: "{}"}, invalidBecause("exit 1")},
	}
	for _, test := range tests {
		if got := readers[test.harness][test.event](test.answer); got != test.want {
			t.Errorf("%s %s %+v: %+v, want %+v", test.harness, test.event, test.answer, got, test.want)
		}
	}
}
