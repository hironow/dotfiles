package main

import (
	"debug/buildinfo"
	"fmt"
	"strings"
)

func verifyBuild(path, version string, target buildTarget) error {
	metadata, err := buildinfo.ReadFile(path)
	if err != nil {
		return fmt.Errorf("read build information: %w", err)
	}
	if metadata.GoVersion != version {
		return fmt.Errorf("build Go version = %q, want %q", metadata.GoVersion, version)
	}
	settings := make(map[string]string)
	for _, setting := range metadata.Settings {
		settings[setting.Key] = setting.Value
		if strings.HasPrefix(setting.Key, "vcs") || (setting.Key == "GOEXPERIMENT" && setting.Value != "") ||
			(setting.Key == "-pgo" && setting.Value != "off" && setting.Value != "") {
			return fmt.Errorf("unexpected build setting %s=%s", setting.Key, setting.Value)
		}
	}
	want := map[string]string{"CGO_ENABLED": "0", "GOOS": target.OS, "GOARCH": target.Arch, "-trimpath": "true"}
	if key, value := target.level(); key != "" {
		want[key] = value
	}
	for key, value := range want {
		if settings[key] != value {
			return fmt.Errorf("build setting %s=%q, want %q", key, settings[key], value)
		}
	}
	return nil
}
