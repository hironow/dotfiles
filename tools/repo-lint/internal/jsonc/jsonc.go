// Package jsonc reads JSON with comments (JSONC), as devcontainer.json and
// .oxlintrc.json are written: `//`, `#` and `/* */` comments and trailing
// commas, outside strings.
package jsonc

import (
	"fmt"
	"strings"

	"github.com/goccy/go-json"
)

// Decode decodes JSONC text.
func Decode(text string) (any, error) {
	var v any
	if err := json.Unmarshal([]byte(Strip(text)), &v); err != nil {
		return nil, fmt.Errorf("decode JSONC: %w", err)
	}
	return v, nil
}

// Strip turns JSONC into JSON: it drops comments and trailing commas outside
// strings, and keeps everything in a string as it is.
func Strip(text string) string {
	var b strings.Builder
	inString, escaped := false, false
	for i := 0; i < len(text); i++ {
		c := text[i]
		switch {
		case inString:
			b.WriteByte(c)
			switch {
			case escaped:
				escaped = false
			case c == '\\':
				escaped = true
			case c == '"':
				inString = false
			}
		case c == '"':
			inString = true
			b.WriteByte(c)
		case strings.HasPrefix(text[i:], "//") || c == '#':
			// A line comment (// or #, as oxlint's json-strip-comments reads
			// it) ends at CR or LF.
			end := strings.IndexAny(text[i:], "\r\n")
			if end < 0 {
				return dropTrailingCommas(b.String())
			}
			i += end - 1
		case strings.HasPrefix(text[i:], "/*"):
			end := strings.Index(text[i+2:], "*/")
			if end < 0 {
				return dropTrailingCommas(b.String())
			}
			b.WriteByte(' ')
			i += end + 3
		default:
			b.WriteByte(c)
		}
	}
	return dropTrailingCommas(b.String())
}

// dropTrailingCommas removes a comma, outside strings, that only whitespace
// separates from a closing } or ].
func dropTrailingCommas(text string) string {
	var b strings.Builder
	inString, escaped := false, false
	for i := 0; i < len(text); i++ {
		c := text[i]
		switch {
		case inString:
			switch {
			case escaped:
				escaped = false
			case c == '\\':
				escaped = true
			case c == '"':
				inString = false
			}
		case c == '"':
			inString = true
		case c == ',':
			rest := strings.TrimLeft(text[i+1:], " \t\r\n")
			if rest != "" && (rest[0] == '}' || rest[0] == ']') {
				continue
			}
		}
		b.WriteByte(c)
	}
	return b.String()
}
