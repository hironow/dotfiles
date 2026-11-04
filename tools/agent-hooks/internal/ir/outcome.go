// Package ir is the internal representation the hooks decide on, the same for
// every harness: here, what a hook decided about one tool call.
package ir

import "strconv"

// Action is what a hook does with a tool call.
type Action int

const (
	// Pass lets the tool call run as it is.
	Pass Action = iota
	// Block stops the tool call and tells the agent why.
	Block
	// Forward writes Outcome.Native, an answer in the harness's own form, as
	// it is. A delegate hook (rtk on Claude and Codex) answers this way: the
	// delegate wrote the answer for that harness.
	Forward
)

func (a Action) String() string {
	switch a {
	case Pass:
		return "pass"
	case Block:
		return "block"
	case Forward:
		return "forward"
	default:
		return "Action(" + strconv.Itoa(int(a)) + ")"
	}
}

// Outcome is what one hook decided about one tool call. The zero Outcome is
// a pass.
type Outcome struct {
	Action Action
	Rule   string // the rule that blocked, for the log, such as "command.pip"; empty on a pass
	Reason string // what the agent is told when the call is blocked; empty on a pass
	Native string // the answer a Forward writes as it is
	Notice string // what a pass reports, such as the formatter's remaining ruff findings
}
