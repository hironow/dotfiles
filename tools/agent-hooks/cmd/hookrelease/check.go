package main

import (
	"debug/buildinfo"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
)

func checkCommand(args []string, stderr io.Writer) int {
	if len(args) == 1 && (args[0] == "--help" || args[0] == "-h") {
		fmt.Fprintln(stderr, "usage: hookrelease check PATH\nRebuild and compare bytes; slower because it uses a fresh temporary GOCACHE.\n"+
			"Exit 0: the same bytes; 1: another release ID than this checkout's; 3: the same ID but other bytes; 2: cannot check.")
		return 0
	}
	code, err := checkRelease(args)
	if err != nil {
		fmt.Fprintln(stderr, "hookrelease check:", err)
	}
	return code
}

func checkRelease(args []string) (int, error) {
	if len(args) != 1 {
		return 2, errors.New("usage: hookrelease check PATH")
	}
	path, err := filepath.Abs(args[0])
	if err != nil {
		return 2, err
	}
	path, err = filepath.EvalSymlinks(path)
	if err != nil {
		return 2, err
	}
	old, err := fileSHA256(path)
	if err != nil {
		return 2, err
	}
	target := buildTarget{OS: runtime.GOOS, Arch: runtime.GOARCH}
	// A damaged header can still be compared as a host release.
	if metadata, err := buildinfo.ReadFile(path); err == nil {
		for _, setting := range metadata.Settings {
			switch setting.Key {
			case "GOOS":
				target.OS = setting.Value
			case "GOARCH":
				target.Arch = setting.Value
			}
		}
	}
	tmp, err := os.MkdirTemp("", "hookrelease-check-*")
	if err != nil {
		return 2, err
	}
	defer os.RemoveAll(tmp)
	plan, err := prepareReleaseInCache(target, filepath.Join(tmp, "cache"))
	if err != nil {
		return 2, err
	}
	id := filepath.Base(filepath.Dir(path))
	if id != plan.id {
		return 1, fmt.Errorf("release ID %s differs from checkout ID %s", id, plan.id)
	}
	rebuilt := filepath.Join(tmp, "agent-hook")
	if target.OS == "windows" {
		rebuilt += ".exe"
	}
	if err := plan.compile(rebuilt); err != nil {
		return 2, err
	}
	fresh, err := fileSHA256(rebuilt)
	if err != nil {
		return 2, err
	}
	// Same ID, other bytes: the release is damaged or was changed. A build
	// never replaces a release in place, so this is not exit 1's "rebuild".
	if old != fresh {
		return 3, fmt.Errorf("release %s has SHA-256 %s, but its rebuild has %s", id, old, fresh)
	}
	return 0, nil
}
