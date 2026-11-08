package definition

import (
	"fmt"
	"slices"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
)

// Rewrite is the rewrite codec: it writes an assignment into a copy of a
// native payload, at its field's first x-ir pointer, and checks the whole
// result against the event's schema. It returns the result. A field the
// definition does not map, a list field, a pointer the payload cannot hold,
// and a result outside the schema are errors; the hook that asked for the
// rewrite answers the pass instead. Members the assignment does not name
// stay as they were.
func (e Event) Rewrite(payload []byte, set ir.Assignment) ([]byte, error) {
	pointers := e.IR[set.Field]
	if len(pointers) == 0 {
		return nil, fmt.Errorf("the %s %s definition maps no field %q", e.harness, e.name, set.Field)
	}
	tokens, ok := pointerTokens(pointers[0])
	if !ok || len(tokens) == 0 || slices.Contains(tokens, wildcard) {
		return nil, fmt.Errorf("field %q is not one value at %q", set.Field, pointers[0])
	}
	var root any
	if err := json.Unmarshal(payload, &root); err != nil {
		return nil, fmt.Errorf("%w: %w", ErrUnreadable, err)
	}
	node := root
	for _, token := range tokens[:len(tokens)-1] {
		object, ok := node.(map[string]any)
		if !ok {
			return nil, fmt.Errorf("%s: %q is under a value that is not an object", pointers[0], token)
		}
		if node, ok = object[token]; !ok {
			return nil, fmt.Errorf("%s: the payload has no member %q", pointers[0], token)
		}
	}
	parent, ok := node.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("%s: the field's parent is not an object", pointers[0])
	}
	parent[tokens[len(tokens)-1]] = set.Value
	merged, err := json.Marshal(root)
	if err != nil {
		return nil, err
	}
	if err := e.Validate(merged); err != nil {
		return nil, fmt.Errorf("the rewritten payload: %w", err)
	}
	return merged, nil
}
