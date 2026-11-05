package main

import (
	"reflect"
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
	if got := normalizedEnvironment(user, buildTarget{OS: "linux", Arch: "amd64"}); !reflect.DeepEqual(got, want) {
		t.Fatalf("environment = %q, want %q", got, want)
	}
}
