package main

import (
	"errors"
	"os"
	"path/filepath"
	"runtime"
)

func dataRoot() (string, error) {
	if runtime.GOOS == "windows" {
		root := os.Getenv("LOCALAPPDATA")
		if !filepath.IsAbs(root) {
			return "", errors.New("LOCALAPPDATA must be absolute")
		}
		return filepath.Join(root, "dotfiles", "agent-hooks"), nil
	}
	if root := os.Getenv("XDG_DATA_HOME"); filepath.IsAbs(root) {
		return filepath.Join(root, "dotfiles", "agent-hooks"), nil
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, ".local", "share", "dotfiles", "agent-hooks"), nil
}
