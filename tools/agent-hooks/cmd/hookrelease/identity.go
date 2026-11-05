package main

import (
	"crypto/sha256"
	"fmt"
	"slices"
	"strings"
)

type buildTarget struct {
	OS, Arch string
}

func (t buildTarget) level() (string, string) {
	switch t.Arch {
	case "amd64":
		return "GOAMD64", "v1"
	case "arm64":
		return "GOARM64", "v8.0"
	case "arm":
		return "GOARM", "7"
	default:
		return "", ""
	}
}

type fileDigest struct {
	Path, SHA256 string
}

func linkFlags(module, id string) string {
	return "-buildid= -s -w -X " + module + "/internal/logline.Release=" + id
}

// releaseID hashes version, target, fixed flags, and sorted input digests.
// The literal <id> avoids putting the resulting ID inside its own input.
func releaseID(version string, target buildTarget, module string, files []fileDigest) string {
	files = slices.Clone(files)
	slices.SortFunc(files, func(a, b fileDigest) int { return strings.Compare(a.Path, b.Path) })
	var canonical strings.Builder
	level, value := target.level()
	fmt.Fprintf(&canonical, "%s\n%s/%s %s=%s\n-trimpath -buildvcs=false -pgo=off -ldflags='%s'\n",
		version, target.OS, target.Arch, level, value, linkFlags(module, "<id>"))
	for _, file := range files {
		fmt.Fprintf(&canonical, "%s %s\n", file.Path, file.SHA256)
	}
	return fmt.Sprintf("%x", sha256.Sum256([]byte(canonical.String())))[:16]
}
