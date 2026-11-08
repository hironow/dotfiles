package definition

import (
	"fmt"
	"sync"

	"github.com/goccy/go-json/jsontext"
	json "github.com/goccy/go-json/v2"
	"github.com/google/jsonschema-go/jsonschema"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/shim"
)

// shimProtocol holds the shim protocol's schemas (package shim), resolved.
type shimProtocol struct {
	request, response *jsonschema.Resolved
}

// loadShimProtocol resolves the shim protocol's schemas once.
var loadShimProtocol = sync.OnceValues(func() (shimProtocol, error) {
	request, err := resolveSchema(shim.RequestV1)
	if err != nil {
		return shimProtocol{}, fmt.Errorf("the shim request schema: %w", err)
	}
	response, err := resolveSchema(shim.ResponseV1)
	if err != nil {
		return shimProtocol{}, fmt.Errorf("the shim response schema: %w", err)
	}
	return shimProtocol{request: request, response: response}, nil
})

func resolveSchema(raw []byte) (*jsonschema.Resolved, error) {
	var schema jsonschema.Schema
	if err := json.Unmarshal(raw, &schema); err != nil {
		return nil, err
	}
	return schema.Resolve(nil)
}

// CheckShimRequest checks a payload as a shim protocol request, on a harness
// reached through a shim (ir.TransportShim): one JSON value, read as Decode
// reads a payload; valid against shim/v1/request.schema.json; and for this
// event's harness and event. An error is a broken exchange: the shim and the
// binary are out of step. A command harness's payload is its own, so it is
// not checked here.
func (e Event) CheckShimRequest(payload []byte) error {
	if e.transport != ir.TransportShim {
		return nil
	}
	var root jsontext.Value
	if err := json.Unmarshal(payload, &root); err != nil {
		return fmt.Errorf("%w: %w", ErrUnreadable, err)
	}
	protocol, err := loadShimProtocol()
	if err != nil {
		return err
	}
	var value any
	if err := json.Unmarshal(root, &value); err != nil {
		return fmt.Errorf("%w: %w", ErrUnreadable, err)
	}
	if err := protocol.request.Validate(value); err != nil {
		return fmt.Errorf("not a shim protocol v1 request: %w", err)
	}
	var names struct {
		Harness string `json:"harness"`
		Event   string `json:"event"`
	}
	if err := json.Unmarshal(root, &names); err != nil {
		return err
	}
	if names.Harness != e.harness || names.Event != e.name {
		return fmt.Errorf("the request is for %s %s, not %s %s", names.Harness, names.Event, e.harness, e.name)
	}
	return nil
}

// Transport returns how the event's harness reaches the binary
// (ir.Transport*).
func (e Event) Transport() string { return e.transport }

// checkShimAnswer checks a shim harness's rendered answer against the
// protocol: it exits 0, and its stdout is one shim protocol v1 response.
func checkShimAnswer(answer Answer) error {
	if answer.Exit != 0 {
		return fmt.Errorf("a shim answer exits %d, not 0", answer.Exit)
	}
	protocol, err := loadShimProtocol()
	if err != nil {
		return err
	}
	var value any
	if err := json.Unmarshal([]byte(answer.Stdout), &value); err != nil {
		return fmt.Errorf("a shim answer is not one JSON value: %w", err)
	}
	if err := protocol.response.Validate(value); err != nil {
		return fmt.Errorf("not a shim protocol v1 response: %w", err)
	}
	return nil
}
