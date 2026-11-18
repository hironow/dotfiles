//go:build windows

package main

import (
	"os"
	"path/filepath"
	"syscall"
	"testing"
)

var (
	kernel32         = syscall.NewLazyDLL("kernel32.dll")
	user32           = syscall.NewLazyDLL("user32.dll")
	getConsoleWindow = kernel32.NewProc("GetConsoleWindow")
	isWindowVisible  = user32.NewProc("IsWindowVisible")
)

func cmdExe(t *testing.T) string {
	t.Helper()
	if comspec := os.Getenv("ComSpec"); comspec != "" {
		return comspec
	}
	return filepath.Join(os.Getenv("SystemRoot"), "System32", "cmd.exe")
}

// Task Scheduler records the exit code of the program it started, so the
// launcher must hand the child's code back unchanged.
func TestRunReturnsTheChildExitCode(t *testing.T) {
	for _, code := range []string{"0", "7"} {
		want := map[string]int{"0": 0, "7": 7}[code]
		if got := run([]string{cmdExe(t), "/c", "exit " + code}); got != want {
			t.Errorf("child exit %s: run returned %d", code, got)
		}
	}
}

// powershell.exe exits 0xFFFD0000 when its -File is missing, and ADR 0042
// reads that last result: a code above 2^31 must survive the round trip
// (os.Exit hands the low 32 bits to ExitProcess).
func TestRunKeepsAnExitCodeAboveTwoToTheThirtyOne(t *testing.T) {
	got := run([]string{cmdExe(t), "/c", "exit -196608"})
	if uint32(got) != 0xFFFD0000 {
		t.Fatalf("child exit 0xFFFD0000: run returned %#x", uint32(got))
	}
}

func TestRunOfAMissingProgramFails(t *testing.T) {
	missing := filepath.Join(t.TempDir(), "does-not-exist.exe")
	if got := run([]string{missing}); got != 1 {
		t.Fatalf("run(%s) = %d, want 1", missing, got)
	}
}

// The child is a console process without a console window: CREATE_NO_WINDOW,
// and SW_HIDE for a child that opens a window of its own.
func TestTheChildStartsWithoutAConsoleWindow(t *testing.T) {
	cmd := command([]string{cmdExe(t), "/c", "exit 0"})
	attr := cmd.SysProcAttr
	if attr == nil || attr.CreationFlags&createNoWindow == 0 || !attr.HideWindow {
		t.Fatalf("SysProcAttr = %+v, want CREATE_NO_WINDOW and HideWindow", attr)
	}
}

// The same, seen from inside the child: it has no console window, or one
// that is not visible.
func TestTheChildHasNoVisibleConsoleWindow(t *testing.T) {
	self, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	t.Setenv("RUN_HIDDEN_TEST_CHILD", "console-window")
	if got := run([]string{self, "-test.run=^TestChildReportsItsConsoleWindow$"}); got != 0 {
		t.Fatalf("the child saw a visible console window (exit %d)", got)
	}
}

// TestChildReportsItsConsoleWindow is the child of the test above: it exits
// 3 when its console window is visible.
func TestChildReportsItsConsoleWindow(t *testing.T) {
	if os.Getenv("RUN_HIDDEN_TEST_CHILD") != "console-window" {
		t.Skip("runs only as the child of TestTheChildHasNoVisibleConsoleWindow")
	}
	window, _, _ := getConsoleWindow.Call()
	if window != 0 {
		if visible, _, _ := isWindowVisible.Call(window); visible != 0 {
			os.Exit(3)
		}
	}
	os.Exit(0)
}
