package logline

import (
	"bytes"
	"errors"
	"fmt"

	json "github.com/goccy/go-json/v2"
)

// Parse reads one JSON object and refuses unknown members.
func Parse(text []byte) (Line, error) {
	text = bytes.TrimSpace(text)
	if len(text) == 0 || text[0] != '{' {
		return Line{}, errors.New("log line must be a JSON object")
	}
	var line Line
	if err := json.Unmarshal(text, &line, json.RejectUnknownMembers(true)); err != nil {
		return Line{}, fmt.Errorf("parse log line: %w", err)
	}
	return line, nil
}
