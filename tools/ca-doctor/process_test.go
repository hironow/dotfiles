package main

import (
	"context"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"
)

func TestProcessCaptureBoundAndCancellation(t *testing.T) {
	exe, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	t.Setenv("CA_DOCTOR_PROCESS_TEST", "1")
	r := OSCommands{}
	result := r.Run(context.Background(), exe, "-test.run=^TestProcessChild$", "--", "flood")
	if !result.Truncated || len(result.Stdout) > captureLimit {
		t.Fatalf("unbounded output: %+v", result)
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	result = r.Run(ctx, exe, "-test.run=^TestProcessChild$", "--", "wait")
	if result.Code == 0 {
		t.Fatal("cancelled process succeeded")
	}
}

func TestVersionProbesDisableKnownAutoInstallMechanisms(t *testing.T) {
	exe, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	t.Setenv("CA_DOCTOR_PROCESS_TEST", "1")
	t.Setenv("GOTOOLCHAIN", "auto")
	result := (OSCommands{}).Run(context.Background(), exe, "-test.run=^TestProcessChild$", "--", "environment")
	if result.Code != 0 || result.Stdout != "local false 0" {
		t.Fatal(result)
	}
}

func TestProcessChild(_ *testing.T) {
	if os.Getenv("CA_DOCTOR_PROCESS_TEST") != "1" {
		return
	}
	switch os.Args[len(os.Args)-1] {
	case "flood":
		os.Stdout.WriteString(strings.Repeat("x", 100000))
	case "wait":
		time.Sleep(time.Hour)
	case "environment":
		os.Stdout.WriteString(os.Getenv("GOTOOLCHAIN") + " " + os.Getenv("MISE_AUTO_INSTALL") + " " + os.Getenv("RUSTUP_AUTO_INSTALL"))
	}
	os.Exit(0)
}

func TestNativePathsAndUnsupportedWindowsWrappers(t *testing.T) {
	if ExecutableSupported("C:\\tools\\shim.cmd", "windows") || ExecutableSupported("a.BAT", "windows") {
		t.Fatal("batch wrapper is not a native executable")
	}
	if !ExecutableSupported("C:\\資料 space\\node.exe", "windows") {
		t.Fatal("native executable rejected")
	}
	if runtime.GOOS == "windows" {
		return
	}
	path := filepath.Join(t.TempDir(), "診断 space")
	if err := os.WriteFile(path, []byte("#!/bin/sh\nprintf accepted"), 0o700); err != nil {
		t.Fatal(err)
	}
	got := (OSCommands{}).Run(context.Background(), path)
	if got.Code != 0 || got.Stdout != "accepted" {
		t.Fatal(got)
	}
}

func TestDescendantHoldingPipeCannotHangChecker(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("Unix process group fixture; Windows runtime test required separately")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	start := time.Now()
	got := (OSCommands{}).Run(ctx, "/bin/sh", "-c", "sleep 30 & wait")
	if got.Code == 0 || time.Since(start) > 2*time.Second {
		t.Fatal(got, time.Since(start))
	}
}
