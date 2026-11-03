// Package bashsubst is what a bash command substitution, $(...), makes of
// the output it captures. The shell guards read every field through one
// (field="$(... | jq -r ...)"), so their ports read fields the same way.
package bashsubst

import "strings"

// Output is printed output as $(...) captures it: bash drops its NUL bytes,
// then every trailing newline.
func Output(printed string) string {
	return strings.TrimRight(strings.ReplaceAll(printed, "\x00", ""), "\n")
}
