package main

import "strings"

// normalizedEnvironment carries only the user's executable path and caches.
func normalizedEnvironment(user []string, target buildTarget) []string {
	values := make(map[string]string)
	for _, entry := range user {
		key, value, _ := strings.Cut(entry, "=")
		values[key] = value
	}
	var env []string
	for _, key := range []string{"PATH", "HOME", "GOCACHE", "GOMODCACHE", "GOPATH"} {
		if value := values[key]; value != "" {
			env = append(env, key+"="+value)
		}
	}
	env = append(env, "GOENV=off", "GOWORK=off", "GOEXPERIMENT=", "GOFLAGS=-mod=readonly", "GOTOOLCHAIN=local",
		"CGO_ENABLED=0", "GOOS="+target.OS, "GOARCH="+target.Arch)
	if key, value := target.level(); key != "" {
		env = append(env, key+"="+value)
	}
	return env
}
