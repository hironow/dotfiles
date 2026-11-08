package logline_test

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logline"
)

// specHMAC encodes the brief's message directly, independently of logline.
func specHMAC(t *testing.T, salt []byte, fields ...string) string {
	t.Helper()
	var message bytes.Buffer
	for _, field := range fields {
		if err := binary.Write(&message, binary.BigEndian, uint32(len(field))); err != nil {
			t.Fatal(err)
		}
		message.WriteString(field)
	}
	mac := hmac.New(sha256.New, salt)
	mac.Write(message.Bytes())
	return hex.EncodeToString(mac.Sum(nil))
}

func salted(f logline.Firing, salt []byte) logline.Line {
	return logline.Build(f, salt, time.Date(2026, 11, 5, 0, 0, 0, 0, time.UTC),
		[8]byte{0xab, 0xcd}, [16]byte{0xde, 0xad})
}

func TestBuildHashesTheProjectDirectoryByPrecedence(t *testing.T) {
	if logline.SaltSize != 32 {
		t.Fatalf("SaltSize = %d; want 32", logline.SaltSize)
	}
	salt := bytes.Repeat([]byte{0x5a}, 32)
	for _, c := range []struct {
		name string
		call *ir.Call
		wd   string
		dir  string
	}{
		{"cwd wins", &ir.Call{Fields: map[string]ir.Value{ir.FieldCwd: stringValue("/cwd")}, Lists: map[string][]ir.Value{ir.ListWorkspaces: {stringValue("/workspace")}}}, "/wd", "/cwd"},
		{"empty string cwd wins", &ir.Call{Fields: map[string]ir.Value{ir.FieldCwd: stringValue("")}, Lists: map[string][]ir.Value{ir.ListWorkspaces: {stringValue("/workspace")}}}, "/wd", ""},
		{"non-string cwd uses workspace", &ir.Call{Fields: map[string]ir.Value{ir.FieldCwd: {Text: "5"}}, Lists: map[string][]ir.Value{ir.ListWorkspaces: {stringValue("/workspace"), stringValue("/second")}}}, "/wd", "/workspace"},
		{"missing cwd uses workspace", &ir.Call{Lists: map[string][]ir.Value{ir.ListWorkspaces: {stringValue("/workspace")}}}, "/wd", "/workspace"},
		{"empty workspace wins", &ir.Call{Lists: map[string][]ir.Value{ir.ListWorkspaces: {stringValue("")}}}, "/wd", ""},
		{"only first workspace counts", &ir.Call{Lists: map[string][]ir.Value{ir.ListWorkspaces: {{Text: "5"}, stringValue("/second")}}}, "/wd", "/wd"},
		{"empty workspaces", &ir.Call{Lists: map[string][]ir.Value{ir.ListWorkspaces: {}}}, "/wd", "/wd"},
		{"no fields", &ir.Call{}, "/wd", "/wd"},
		{"nil call", nil, "/wd", "/wd"},
		{"no directory", nil, "", ""},
	} {
		t.Run(c.name, func(t *testing.T) {
			got := salted(logline.Firing{Call: c.call, Wd: c.wd}, salt)
			want := ""
			if c.dir != "" {
				want = specHMAC(t, salt, "project", c.dir)[:16]
			}
			if got.Project != want {
				t.Errorf("project = %q; want %q", got.Project, want)
			}
		})
	}
}

func TestBuildHashesTypedIDsAndTheLoggedHarness(t *testing.T) {
	salt := bytes.Repeat([]byte{0x5a}, 32)
	traces := make(map[string]bool)
	for _, c := range []struct {
		name, harness, logged, sessionText, callText string
		session, call                                ir.Value
	}{
		{"strings", "claude", "claude", "s5", "s6", stringValue("5"), stringValue("6")},
		{"number session", "claude", "claude", "j5", "s6", ir.Value{Text: "5"}, stringValue("6")},
		{"number call", "claude", "claude", "s5", "j6", stringValue("5"), ir.Value{Text: "6"}},
		{"other JSON", "agy", "agy", "jnull", `j{"a":1}`, ir.Value{Text: "null"}, ir.Value{Text: `{"a":1}`}},
		{"empty ids are present", "pi", "pi", "s", "s", stringValue(""), stringValue("")},
		{"unknown harness", "secret-marker", "other", "s5", "s6", stringValue("5"), stringValue("6")},
		{"length prefixes left", "codex", "codex", "sab", "sc", stringValue("ab"), stringValue("c")},
		{"length prefixes right", "codex", "codex", "sa", "sbc", stringValue("a"), stringValue("bc")},
	} {
		t.Run(c.name, func(t *testing.T) {
			f := logline.Firing{Harness: c.harness, Event: "pre", Call: &ir.Call{
				Harness: "ignored", Fields: map[string]ir.Value{ir.FieldSessionID: c.session, ir.FieldCallID: c.call},
			}}
			got := salted(f, salt)
			want := specHMAC(t, salt, "trace", c.logged, c.sessionText, c.callText)[:32]
			if got.TraceID != want || traces[got.TraceID] {
				t.Errorf("trace = %q; want distinct %q", got.TraceID, want)
			}
			traces[got.TraceID] = true
			f.Event = "post"
			if post := salted(f, salt); post.TraceID != got.TraceID {
				t.Errorf("pre/post trace differs: %q / %q", got.TraceID, post.TraceID)
			}
		})
	}
}

func TestBuildUsesFallbackIDsWithoutACompleteSaltedIdentity(t *testing.T) {
	complete := logline.Firing{Harness: "claude", Wd: "/project", Call: &ir.Call{Fields: map[string]ir.Value{
		ir.FieldSessionID: stringValue("session"), ir.FieldCallID: stringValue("call"),
	}}}
	for _, salt := range [][]byte{nil, {}, bytes.Repeat([]byte{1}, 31), bytes.Repeat([]byte{1}, 33)} {
		got := salted(complete, salt)
		if got.Project != "" || got.TraceID != "dead0000000000000000000000000000" || got.SpanID != "abcd000000000000" {
			t.Errorf("salt length %d: got %#v", len(salt), got)
		}
	}
	salt := bytes.Repeat([]byte{1}, 32)
	for _, call := range []*ir.Call{
		nil,
		{},
		{Fields: map[string]ir.Value{ir.FieldSessionID: stringValue("session")}},
		{Fields: map[string]ir.Value{ir.FieldCallID: stringValue("call")}},
	} {
		if got := salted(logline.Firing{Call: call}, salt).TraceID; got != "dead0000000000000000000000000000" {
			t.Errorf("incomplete identity = %q", got)
		}
	}
	complete.Usage = true
	got := members(t, salted(complete, salt))
	if len(got) != 6 || got["traceId"] != "dead0000000000000000000000000000" {
		t.Errorf("salted usage must keep only its six keys and fallback trace: %#v", got)
	}
}
