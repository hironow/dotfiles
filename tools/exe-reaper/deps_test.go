package main

import (
	"os/exec"
	"strings"
	"testing"
)

// thisModule is the import path every non-standard package this binary links
// must start with.
const thisModule = "github.com/hironow/dotfiles/tools/exe-reaper"

// The money stop links the standard library and this module, and nothing else.
// That was Phase 3's trust argument for the binary that shrinks the pool: it
// has no dependency tree to trust. L1 needs gRPC stubs for AX and Substrate,
// so the module now requires them (plan D1), and only cmd/exe-reap may import
// the packages that use them. This test is what keeps "only".
func TestTheMoneyStopLinksOnlyTheStandardLibrary(t *testing.T) {
	out, err := exec.Command("go", "list", "-deps", "-f", "{{if not .Standard}}{{.ImportPath}}{{end}}", ".").Output()
	if err != nil {
		t.Fatalf("go list -deps: %v", err)
	}
	for _, pkg := range strings.Fields(string(out)) {
		if pkg != thisModule && !strings.HasPrefix(pkg, thisModule+"/") {
			t.Errorf("exe-reaper links %s; the binary that stops the pool may link only the standard library and this module", pkg)
		}
	}
}
