// Package fake holds working in-memory stand-ins for the ports the binary's
// shell reaches the outside through. Tests use them; nothing here touches the
// machine.
package fake

import "github.com/hironow/dotfiles/tools/agent-hooks/internal/fileguard"

// Machine is a launch.Machine whose basename(1) flavor is a field. It counts
// how often it was asked, so a test can check that the shell asks only when
// a path needs the answer.
type Machine struct {
	Flavor fileguard.Basename
	Probes int
}

// Basename returns the flavor the test set.
func (m *Machine) Basename() fileguard.Basename {
	m.Probes++
	return m.Flavor
}
