package logline_test

import (
	"bytes"
	"strings"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logline"
)

func TestBuildNeverLeaksRawMarkers(t *testing.T) {
	credential := "AK" + "IA" + strings.Repeat("Q", 16)
	markers := []string{"/Users/secret-marker/x.go", "curl secret-marker", credential, "gitsecret-marker", ".gosecret-marker"}
	for _, marker := range markers {
		for _, c := range []struct {
			name, kind, command, path, harness string
			usage                              bool
		}{
			{"every raw field", marker, marker, marker, marker, false},
			{"shell", ir.KindShell, marker, marker, "claude", false},
			{"shell arguments", ir.KindShell, "git " + marker, marker, "claude", false},
			{"write", ir.KindWrite, marker, marker, "claude", false},
			{"edit", ir.KindEdit, marker, marker, "claude", false},
			{"notebook", ir.KindNotebook, marker, marker, "claude", false},
			{"patch", ir.KindPatch, "*** Begin Patch\n*** Add File: " + marker + "\n+" + marker + "\n*** End Patch\n", marker, "codex", false},
			{"usage", marker, marker, marker, marker, true},
		} {
			t.Run(c.name+"/"+marker, func(t *testing.T) {
				f := logline.Firing{
					Usage: c.usage, Harness: c.harness, Event: marker, Hook: marker, Error: marker, Mismatch: marker, Wd: marker,
					Call: &ir.Call{
						Harness: marker, Event: marker, HookCwd: marker, Transport: marker, PathResolution: marker,
						Tool: marker, Kind: c.kind, Native: []byte(marker),
						Fields: map[string]ir.Value{
							ir.FieldCommand: stringValue(c.command), ir.FieldFilePath: stringValue(c.path),
							ir.FieldNotebookPath: stringValue(c.path), ir.FieldContent: stringValue(marker),
							ir.FieldCwd: stringValue(marker), ir.FieldSessionID: stringValue(marker),
							ir.FieldCallID: {Text: marker}, marker: stringValue(marker),
						},
						Lists: map[string][]ir.Value{
							ir.ListContents:   {stringValue(marker), {Text: marker}},
							ir.ListWorkspaces: {stringValue(marker), {Text: marker}}, marker: {stringValue(marker)},
						},
					},
					Outcome: ir.Outcome{
						Action: ir.Rewrite, Rule: marker, Reason: marker, Native: marker,
						Notice: marker, Set: ir.Assignment{Field: marker, Value: marker},
					},
				}
				for _, salt := range [][]byte{nil, bytes.Repeat([]byte{1}, 32)} {
					encoded, err := salted(f, salt).Marshal()
					if err != nil {
						t.Fatal(err)
					}
					lower := strings.ToLower(string(encoded))
					for _, forbidden := range append(markers, "secret-marker") {
						if strings.Contains(lower, strings.ToLower(forbidden)) {
							t.Fatalf("raw marker reached the log: %s", encoded)
						}
					}
				}
			})
		}
	}
}

func TestBuildLongestListedLinesStayBelow4096Bytes(t *testing.T) {
	// Pick the longest independent enum values, including an allowed tool
	// with a different mapped kind. Build checks membership, not mapping.
	longest := func(words string) string {
		result := ""
		for word := range strings.FieldsSeq(words) {
			if len(word) > len(result) {
				result = word
			}
		}
		return result
	}
	command := ""
	for program := range strings.FieldsSeq(listedPrograms) {
		candidate := program + " " + longest(listedSubcommands[program])
		if len(candidate) > len(command) {
			command = candidate
		}
	}
	for _, kind := range []string{ir.KindShell, ir.KindWrite, ir.KindEdit, ir.KindNotebook, ir.KindPatch} {
		f := logline.Firing{
			Harness: "claude", Event: "unknown", Hook: "secrets-guard", Duration: time.Duration(-1 << 63),
			Outcome: ir.Outcome{Action: ir.Forward, Rule: "command.gcloud-infra"},
			Error:   logline.ErrInputUnreadable, Mismatch: logline.MismatchUnchecked, Wd: "/project",
			Call: &ir.Call{Tool: "NotebookEdit", Kind: kind, Fields: map[string]ir.Value{
				ir.FieldCommand: stringValue(command), ir.FieldFilePath: stringValue("file" + longest(listedExtensions)),
				ir.FieldNotebookPath: stringValue("file" + longest(listedExtensions)),
				ir.FieldSessionID:    stringValue("session"), ir.FieldCallID: stringValue("call"),
			}},
		}
		if kind == ir.KindPatch {
			f.Call.Fields[ir.FieldCommand] = stringValue("*** Begin Patch\n*** Add File: file" + longest(listedExtensions) + "\n")
		}
		line := logline.Build(f, bytes.Repeat([]byte{1}, 32), time.Date(9999, 12, 31, 23, 59, 59, 999999999, time.UTC),
			[8]byte{0xff}, [16]byte{0xff})
		encoded, err := line.Marshal()
		if err != nil {
			t.Fatal(err)
		}
		if len(encoded) >= 4096 {
			t.Fatalf("%s line is %d bytes; want under 4096", kind, len(encoded))
		}
		t.Logf("longest %s line: %d bytes", kind, len(encoded))
	}
}
