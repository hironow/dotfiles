// Package logsink stores the binary's log lines without interpreting their fields.
package logsink

import "time"

const (
	// MaxLine is the exclusive byte limit for a line, including its newline.
	MaxLine = 4096
	// DayCap is the soft byte limit for a day's file. Concurrent writes may exceed it.
	DayCap = 10 << 20
	// KeepDays is the oldest day offset retained, including the boundary day.
	KeepDays = 14
	// SaltSize is the number of random bytes in the machine's salt.
	SaltSize = 32
)

// Sink is the port the binary logs through.
type Sink interface {
	// Salt returns the machine's salt, or false when it is unavailable.
	Salt() ([]byte, bool)
	// Write appends a newline-terminated line shorter than MaxLine to now's UTC day.
	// It then removes day files more than KeepDays older than that day.
	Write(now time.Time, line []byte) error
}
