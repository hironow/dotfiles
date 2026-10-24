package main

import (
	"runtime/debug"
	"strings"
)

func moduleEvidence(info *debug.BuildInfo) []Evidence {
	evidence := []Evidence{{"go-build", info.GoVersion}}
	modules := append([]*debug.Module{&info.Main}, info.Deps...)
	for _, dep := range modules {
		if !strings.Contains(strings.ToLower(dep.Path), "brotli") && (dep.Replace == nil || !strings.Contains(strings.ToLower(dep.Replace.Path), "brotli")) {
			continue
		}
		detail := dep.Path + "@" + dep.Version
		if dep.Replace != nil {
			detail += " => " + dep.Replace.Path + "@" + dep.Replace.Version
		}
		evidence = append(evidence, Evidence{"go-module", detail})
	}
	return evidence
}
