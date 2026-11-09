//go:build linux

package main

import (
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

// TestHelperRunsWhileItsBinaryIsSynced is not a test of its own: the test
// below runs a copy of this test binary with this one selected, so that the
// copy is a running program while it is synced.
func TestHelperRunsWhileItsBinaryIsSynced(_ *testing.T) {
	if os.Getenv("HOOKRELEASE_SYNC_HELPER") != "1" {
		return
	}
	// Bound the helper even when the test below fails to stop it.
	time.Sleep(10 * time.Second)
}

func TestSyncFileSyncsABinaryThatIsRunning(t *testing.T) {
	// given a copy of this test binary, running, as the binary a release
	// build syncs has just run its own checks (and on Linux the kernel can
	// hold it as running a moment after the process has exited)
	self, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	binary := filepath.Join(t.TempDir(), "agent-hook")
	copyExecutable(t, self, binary)
	// Audited: binary is this test binary's own copy in the test's temporary
	// directory, and the argument is fixed; no shell runs.
	// nosemgrep: dangerous-exec-command, go.lang.security.audit.dangerous-exec-command.dangerous-exec-command
	helper := exec.Command(binary, "-test.run=^TestHelperRunsWhileItsBinaryIsSynced$")
	// The helper is killed, so its TestMain cannot remove what it made:
	// point its temporary directory at one this test removes.
	helper.Env = append(os.Environ(), "HOOKRELEASE_SYNC_HELPER=1", "TMPDIR="+t.TempDir())
	if err := helper.Start(); err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		_ = helper.Process.Kill()
		_ = helper.Wait()
	})
	// when the release build syncs it, then it syncs: Linux's fsync needs no
	// write access, and opening a running binary for writing is ETXTBSY
	if err := (systemDisk{}).SyncFile(binary); err != nil {
		t.Fatal(err)
	}
}

func copyExecutable(t *testing.T, from, to string) {
	t.Helper()
	source, err := os.Open(from)
	if err != nil {
		t.Fatal(err)
	}
	defer source.Close()
	target, err := os.OpenFile(to, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o755)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := io.Copy(target, source); err != nil {
		target.Close()
		t.Fatal(err)
	}
	// Closed before it runs: a program cannot start while a writer holds it.
	if err := target.Close(); err != nil {
		t.Fatal(err)
	}
}
