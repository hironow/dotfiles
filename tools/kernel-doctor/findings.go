package main

import (
	"fmt"
	"io"
	"strings"
)

// Finding is one line of the doctor protocol: `LEVEL name - detail`, LEVEL
// padded to four. scripts/doctor_lines.py defines both the writer and the
// reader; this file is the writer for kernel-doctor.
type Finding struct {
	Level  string `json:"level"`
	Name   string `json:"name"`
	Detail string `json:"detail"`
}

func (f Finding) String() string {
	return fmt.Sprintf("%-4s %s - %s", f.Level, clean(f.Name), clean(f.Detail))
}

// Control characters would let a kernel version string (an untrusted input
// when it comes from --osrelease) forge a second doctor line.
func clean(s string) string {
	return strings.Map(func(r rune) rune {
		if r < 32 || r == 127 {
			return ' '
		}
		return r
	}, s)
}

// Report writes findings and returns the exit code.
//
// There is deliberately no ERR path. This repository does not ship, build or
// pin a Linux kernel, so a finding here is never something `just doctor` may
// fail on: `just doctor` exiting 1 would break `just self-check` and
// test_doctor_sandbox, both of which assert exit 0, over a condition only the
// operator can fix and only outside this repository. A version comparison that
// cannot be made is reported as WARN, never as a verdict. See ADR-0065.
func Report(out io.Writer, findings []Finding) int {
	code := 0
	for _, f := range findings {
		if _, err := fmt.Fprintln(out, f.String()); err != nil {
			return 1
		}
		if f.Level != "OK" && code == 0 {
			code = 1
		}
	}
	return code
}
