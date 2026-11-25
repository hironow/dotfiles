package rules

import (
	"maps"
	"path"
	"regexp"
	"slices"
	"strings"
)

const (
	dependabotPath = ".github/dependabot.yaml"
	allDockerfiles = "**/Dockerfile*"
)

var (
	// registryHost is a domain of two or more dot-joined components with an
	// optional port: dependabot-core's REGISTRY in
	// docker/lib/dependabot/shared/shared_file_parser.rb.
	registryHost = regexp.MustCompile(`^[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?::\d+)?$`)
	fromLine     = regexp.MustCompile(`(?mi)^FROM\s+(?:--platform=\S+\s+)?(\S+)`)
)

// heldPythonUpdates is what the docker ignore skips for a python base image.
var heldPythonUpdates = []string{"version-update:semver-major", "version-update:semver-minor"}

// dependabotName is the dependency name Dependabot gives an image reference.
// The digest and the tag are dropped (a tag is a colon in the last path
// component; one in the first is a registry port), and so is a leading
// registry: the FROM docker.io/library/python:3.12.15-slim is library/python.
func dependabotName(ref string) string {
	ref, _, _ = strings.Cut(ref, "@")
	head, last := "", ref
	if i := strings.LastIndex(ref, "/"); i >= 0 {
		head, last = ref[:i+1], ref[i+1:]
	}
	last, _, _ = strings.Cut(last, ":")
	ref = head + last
	if first, rest, ok := strings.Cut(ref, "/"); ok && rest != "" && registryHost.MatchString(first) {
		return rest
	}
	return ref
}

// ignoredUpdates is each ignored dependency name and the update types its
// ignore lists (none: every update is ignored).
func ignoredUpdates(entry map[string]any) map[string][]string {
	out := map[string][]string{}
	for _, item := range tables(entry, "ignore") {
		if name, ok := str(item, "dependency-name"); ok {
			out[name] = strs(item, "update-types")
		}
	}
	return out
}

// watched reports whether an entry's directory glob matches dir.
func watched(dirs []string, dir string) bool {
	return slices.ContainsFunc(dirs, func(d string) bool {
		ok, _ := path.Match(strings.TrimPrefix(d, "/"), dir)
		return ok
	})
}

// dependabotPythonHeld: the compiled dependencies of emulator/a2a-inspector
// (cffi, pydantic-core, asyncpg) have no wheels for newer Pythons, so a minor
// bump builds them from sdist and fails in a slim image. The ignore matches
// Dependabot's dependency name, not the FROM text (PR #652).
func dependabotPythonHeld() Rule {
	const id = "dependabot-python-images-held-on-minor"
	return Rule{
		ID:  id,
		Why: "the docker Dependabot entry keeps every python base image on its minor; compiled deps lack wheels for newer Pythons",
		Inputs: []Input{
			{Path: dependabotPath, Format: YAML},
			{Path: allDockerfiles, Format: Text, Glob: true},
		},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: dependabotPath}
			var docker map[string]any
			for _, entry := range tables(in[dependabotPath], "updates") {
				if eco, _ := str(entry, "package-ecosystem"); eco == "docker" {
					docker = entry
					break
				}
			}
			if docker == nil {
				r.add("dependabot.yaml has no docker entry")
				return r.out
			}
			ignored := ignoredUpdates(docker)
			dirs := directories(docker)
			files, _ := in[allDockerfiles].(map[string]any)
			images := 0
			for _, file := range slices.Sorted(maps.Keys(files)) {
				if !watched(dirs, path.Dir(file)) {
					continue
				}
				text, _ := files[file].(string)
				for _, m := range fromLine.FindAllStringSubmatch(text, -1) {
					name := dependabotName(m[1])
					if path.Base(name) != "python" {
						continue
					}
					images++
					if skipped := ignored[name]; !containsAll(skipped, heldPythonUpdates) {
						r.addAt(file, "Dependabot names this python image %q; the docker ignore must skip %v for it", name, heldPythonUpdates)
					}
				}
			}
			if images == 0 {
				r.add("no python base image in the docker directories; the directories or the FROM lines changed")
			}
			return r.out
		},
	}
}

func containsAll(have, want []string) bool {
	for _, w := range want {
		if !slices.Contains(have, w) {
			return false
		}
	}
	return true
}

// dependabotUVSyncedTools: ruff and ty are pinned == in four places (the root,
// emulator and RTTM lint groups, and mise) and `just bump-tool` bumps them
// together, so no uv entry may bump one place alone.
func dependabotUVSyncedTools() Rule {
	const id = "dependabot-uv-skips-synced-tools"
	return Rule{
		ID:     id,
		Why:    "ruff and ty are bumped in four places together by `just bump-tool`, so every uv Dependabot entry ignores them",
		Inputs: []Input{{Path: dependabotPath, Format: YAML}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: dependabotPath}
			uv := map[string]map[string]any{}
			for _, entry := range tables(in[dependabotPath], "updates") {
				if eco, _ := str(entry, "package-ecosystem"); eco == "uv" {
					dir, _ := str(entry, "directory")
					uv[dir] = entry
				}
			}
			for _, project := range []string{"/", "/emulator", "/tools/rttm"} {
				entry, ok := uv[project]
				if !ok {
					r.add("dependabot.yaml has no uv entry for %s", project)
					continue
				}
				ignored := ignoredUpdates(entry)
				for _, tool := range []string{"ruff", "ty"} {
					if types, ok := ignored[tool]; !ok || len(types) > 0 {
						r.add("the uv entry for %s must ignore %s, every update of it", project, tool)
					}
				}
			}
			return r.out
		},
	}
}
