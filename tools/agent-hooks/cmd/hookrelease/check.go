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
	code, err := checkRelease(args, stderr)
	if err != nil {
		fmt.Fprintln(stderr, "hookrelease check:", err)
	}
	return code
}

func checkRelease(args []string, stderr io.Writer) (int, error) {
	if len(args) != 1 {
		return 2, errors.New("usage: hookrelease check PATH")
	}
	path, err := filepath.Abs(args[0])
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
	plan, err := prepareRelease(target)
	if err != nil {
		return 2, err
	}
	id := filepath.Base(filepath.Dir(path))
	if id != plan.id {
		return 1, fmt.Errorf("release ID %s differs from checkout ID %s", id, plan.id)
	}
	tmp, err := os.MkdirTemp("", "hookrelease-check-*")
	if err != nil {
		return 2, err
	}
	defer os.RemoveAll(tmp)
	rebuilt, err := plan.build(tmp, stderr)
	if err != nil {
		return 2, err
	}
	fresh, err := fileSHA256(rebuilt)
	if err != nil {
		return 2, err
	}
	if old != fresh {
		return 1, fmt.Errorf("release %s has different SHA-256: %s != %s", id, old, fresh)
	}
	return 0, nil
}
