package logsink

import (
	"path/filepath"
	"runtime"
)

// Base returns an absolute state directory from lookupEnv (os.LookupEnv in the binary).
// Windows uses LOCALAPPDATA. Unix prefers XDG_STATE_HOME, then HOME/.local/state.
func Base(lookupEnv func(string) (string, bool)) (string, bool) {
	if runtime.GOOS == "windows" {
		path, ok := lookupEnv("LOCALAPPDATA")
		if ok && filepath.IsAbs(path) {
			return path, true
		}
		return "", false
	}
	if path, ok := lookupEnv("XDG_STATE_HOME"); ok && filepath.IsAbs(path) {
		return path, true
	}
	if home, ok := lookupEnv("HOME"); ok && filepath.IsAbs(home) {
		return filepath.Join(home, ".local", "state"), true
	}
	return "", false
}
