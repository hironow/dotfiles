package main

import "strings"

// normalizedEnvironment carries executable paths, caches, and Windows' required host directories.
func normalizedEnvironment(user []string, target buildTarget, hostOS string) []string {
	values := make(map[string]string)
	for _, entry := range user {
		key, value, _ := strings.Cut(entry, "=")
		if hostOS == "windows" {
			key = strings.ToUpper(key)
		}
		values[key] = value
	}
	var env []string
	keys := []string{"PATH", "HOME", "GOCACHE", "GOMODCACHE", "GOPATH"}
	if hostOS == "windows" {
		keys = append(keys, "TMP", "TEMP", "USERPROFILE", "LOCALAPPDATA", "SystemRoot")
	}
	for _, key := range keys {
		if value := values[strings.ToUpper(key)]; value != "" {
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
