//go:build darwin

package logsink

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// grant gives everyone an ACL entry on the path with /bin/chmod +a.
func grant(t *testing.T, path, entry string) {
	t.Helper()
	// Audited: /bin/chmod with this test's own path and a literal entry.
	if out, err := exec.Command("/bin/chmod", "+a", entry, path).CombinedOutput(); err != nil {
		t.Fatalf("chmod +a %q %s: %v: %s", entry, path, err, out)
	}
}

// aclOf is the path's ACL entries as /bin/ls -lde prints them (lines that
// start with a number and a colon), as a check that does not use the code
// under test.
func aclOf(t *testing.T, path string) []string {
	t.Helper()
	// Audited: /bin/ls with this test's own path.
	out, err := exec.Command("/bin/ls", "-lde", path).CombinedOutput()
	if err != nil {
		t.Fatalf("ls -lde %s: %v: %s", path, err, out)
	}
	var entries []string
	for _, line := range strings.Split(string(out), "\n")[1:] {
		if strings.TrimSpace(line) != "" {
			entries = append(entries, strings.TrimSpace(line))
		}
	}
	return entries
}

func TestClearACLRemovesEveryEntryAndLeavesAFileWithoutOneAlone(t *testing.T) {
	dir := t.TempDir()
	for _, entry := range []string{"everyone allow read", "everyone deny write"} {
		path := filepath.Join(dir, strings.ReplaceAll(entry, " ", "-"))
		if err := os.WriteFile(path, []byte("x"), 0o600); err != nil {
			t.Fatal(err)
		}
		// given a file with an ACL entry, opened as the sink opens it
		grant(t, path, entry)
		file, err := os.Open(path)
		if err != nil {
			t.Fatal(err)
		}
		// when the sink clears its ACL through the handle
		err = clearACL(file)
		_ = file.Close()
		// then no entry is left, and the mode bits are as they were
		if err != nil {
			t.Fatalf("%s: clearACL: %v", entry, err)
		}
		if got := aclOf(t, path); len(got) != 0 {
			t.Errorf("%s: the ACL still holds %q", entry, got)
		}
		if info, err := os.Stat(path); err != nil || info.Mode().Perm() != 0o600 {
			t.Errorf("%s: mode %v (%v), want 0600", entry, info.Mode().Perm(), err)
		}
	}
	// A file without an ACL is left as it is.
	plain := filepath.Join(dir, "plain")
	if err := os.WriteFile(plain, []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}
	file, err := os.Open(plain)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	if has, err := hasACL(file); err != nil || has {
		t.Fatalf("hasACL on a plain file = %v, %v; want false", has, err)
	}
	if err := clearACL(file); err != nil {
		t.Fatalf("clearACL on a plain file: %v", err)
	}
}

func TestTheFileSinkRemovesACLsItFindsOrInherits(t *testing.T) {
	base := t.TempDir()
	// given a base whose ACL lets everyone read, and passes that on to
	// everything made in it
	grant(t, base, "everyone allow list,search,read,file_inherit,directory_inherit")
	// and a logs directory and a day file made before, with their own grants
	hooks := filepath.Join(base, "dotfiles", "agent-hooks")
	logs := filepath.Join(hooks, "logs")
	if err := os.MkdirAll(logs, 0o700); err != nil {
		t.Fatal(err)
	}
	now := time.Date(2026, 11, 5, 4, 0, 0, 0, time.UTC)
	day := filepath.Join(logs, "2026-11-05.jsonl")
	if err := os.WriteFile(day, nil, 0o600); err != nil {
		t.Fatal(err)
	}
	grant(t, day, "everyone allow read")
	if len(aclOf(t, logs)) == 0 || len(aclOf(t, day)) == 0 {
		t.Fatal("the setup did not give the directories and the file an ACL")
	}
	// when the sink opens, makes its salt, and writes a line
	sink, err := OpenFileSink(base, os.Getuid())
	if err != nil {
		t.Fatal(err)
	}
	defer sink.Close()
	if _, ok := sink.Salt(); !ok {
		t.Fatal("Salt() = false")
	}
	if err := sink.Write(now, []byte("{}\n")); err != nil {
		t.Fatal(err)
	}
	// then none of its directories and files keeps an ACL
	for _, path := range []string{hooks, logs, day, filepath.Join(hooks, "salt"), filepath.Join(hooks, "salt.lock")} {
		if got := aclOf(t, path); len(got) != 0 {
			t.Errorf("%s keeps the ACL %q", path, got)
		}
	}
	if data, err := os.ReadFile(day); err != nil || string(data) != "{}\n" {
		t.Errorf("the day's file holds %q (%v), want the line", data, err)
	}
}
