//go:build darwin

package logsink

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
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

func TestRestrictLeavesAFileToItsOwnerInOneStep(t *testing.T) {
	dir := t.TempDir()
	cases := []struct {
		entry string
		mode  os.FileMode
	}{
		{"everyone allow read", 0o600},
		{"everyone deny write", 0o600},
		// A loose mode guarded by a deny entry for another user (an entry
		// for everyone would deny the owner too): the mode and the ACL change
		// in the same call, so the file is never open in between.
		{"user:nobody deny read", 0o644},
	}
	for _, c := range cases {
		path := filepath.Join(dir, strings.NewReplacer(" ", "-", ":", "-").Replace(c.entry))
		if err := os.WriteFile(path, []byte("x"), c.mode); err != nil {
			t.Fatal(err)
		}
		if err := os.Chmod(path, c.mode); err != nil {
			t.Fatal(err)
		}
		// given a file with an ACL entry, opened as the sink opens it
		grant(t, path, c.entry)
		file, err := os.Open(path)
		if err != nil {
			t.Fatal(err)
		}
		// when the sink restricts it through the handle
		err = restrict(file, c.mode, 0o600)
		_ = file.Close()
		// then no entry is left, and the mode is the owner's only
		if err != nil {
			t.Fatalf("%s: restrict: %v", c.entry, err)
		}
		if got := aclOf(t, path); len(got) != 0 {
			t.Errorf("%s: the ACL still holds %q", c.entry, got)
		}
		if info, err := os.Stat(path); err != nil || info.Mode().Perm() != 0o600 {
			t.Errorf("%s: mode %v (%v), want 0600", c.entry, info.Mode().Perm(), err)
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
	before, err := file.Stat()
	if err != nil {
		t.Fatal(err)
	}
	if err := restrict(file, 0o600, 0o600); err != nil {
		t.Fatalf("restrict on a plain file: %v", err)
	}
	// Nothing was written: its change time is the same.
	after, err := file.Stat()
	if err != nil {
		t.Fatal(err)
	}
	if b, a := before.Sys().(*syscall.Stat_t), after.Sys().(*syscall.Stat_t); b.Ctimespec != a.Ctimespec {
		t.Errorf("restrict changed a file that needed nothing (ctime %v to %v)", b.Ctimespec, a.Ctimespec)
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
	// and agent-hooks and a salt left open by their modes, guarded only by
	// deny entries for another user
	if err := os.Chmod(hooks, 0o755); err != nil {
		t.Fatal(err)
	}
	grant(t, hooks, "user:nobody deny list,search")
	salt := filepath.Join(hooks, "salt")
	if err := os.WriteFile(salt, bytes.Repeat([]byte{9}, SaltSize), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(salt, 0o644); err != nil {
		t.Fatal(err)
	}
	grant(t, salt, "user:nobody deny read")
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
	if got, ok := sink.Salt(); !ok || !bytes.Equal(got, bytes.Repeat([]byte{9}, SaltSize)) {
		t.Fatalf("Salt() = %x, %v; want the salt that was there", got, ok)
	}
	if err := sink.Write(now, []byte("{}\n")); err != nil {
		t.Fatal(err)
	}
	// then none of its directories and files keeps an ACL, and each is its
	// owner's alone
	for path, mode := range map[string]os.FileMode{hooks: 0o700, logs: 0o700, day: 0o600, salt: 0o600} {
		if got := aclOf(t, path); len(got) != 0 {
			t.Errorf("%s keeps the ACL %q", path, got)
		}
		if info, err := os.Stat(path); err != nil || info.Mode().Perm() != mode {
			t.Errorf("%s has mode %v (%v), want %v", path, info.Mode().Perm(), err, mode)
		}
	}
	if data, err := os.ReadFile(day); err != nil || string(data) != "{}\n" {
		t.Errorf("the day's file holds %q (%v), want the line", data, err)
	}
}
