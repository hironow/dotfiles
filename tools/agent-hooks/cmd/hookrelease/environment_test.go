package main

import (
	"reflect"
	"strings"
	"testing"
)

func TestGoEnvironmentDropsAmbientSettings(t *testing.T) {
	user := []string{
		"PATH=/tools", "HOME=/home/test", "GOCACHE=/cache", "GOMODCACHE=/modules", "GOPATH=/gopath",
		"GOFLAGS=-tags=x", "GOEXPERIMENT=invalid", "GOWORK=/parent/go.work", "GOENV=/settings",
		"CGO_ENABLED=1", "GOAMD64=v4", "GOARM64=v9.0", "GOPROXY=https://example.invalid", "SECRET=private",
	}
	want := []string{
		"PATH=/tools", "HOME=/home/test", "GOCACHE=/cache", "GOMODCACHE=/modules", "GOPATH=/gopath",
		"GOENV=off", "GOWORK=off", "GOEXPERIMENT=", "GOFLAGS=-mod=readonly", "GOTOOLCHAIN=local",
		"CGO_ENABLED=0", "GOOS=linux", "GOARCH=amd64", "GOAMD64=v1",
	}
	if got := normalizedEnvironment(user, buildTarget{OS: "linux", Arch: "amd64"}, "linux"); !reflect.DeepEqual(got, want) {
		t.Fatalf("environment = %q, want %q", got, want)
	}
}

func TestWindowsEnvironmentIsCarriedOnlyOnWindows(t *testing.T) {
	keys := []string{"TMP", "TEMP", "USERPROFILE", "LOCALAPPDATA", "SystemRoot"}
	user := []string{"Path=tools"}
	for _, key := range keys {
		user = append(user, key+"=windows-"+key)
	}
	for _, hostOS := range []string{"windows", "linux"} {
		t.Run(hostOS, func(t *testing.T) {
			got := make(map[string]string)
			for _, entry := range normalizedEnvironment(user, buildTarget{OS: "windows", Arch: "amd64"}, hostOS) {
				key, value, _ := strings.Cut(entry, "=")
				got[key] = value
			}
			for _, key := range keys {
				want := ""
				if hostOS == "windows" {
					want = "windows-" + key
				}
				if got[key] != want {
					t.Errorf("%s = %q, want %q", key, got[key], want)
				}
			}
			if hostOS == "windows" && got["PATH"] != "tools" {
				t.Errorf("Windows Path was dropped: %v", got)
			}
		})
	}
}
