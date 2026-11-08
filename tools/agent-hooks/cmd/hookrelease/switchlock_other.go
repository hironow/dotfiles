//go:build !unix

package main

import (
	"errors"
	"fmt"
)

// switchLock has no implementation here: switch refuses Windows until its
// own PR, which brings a lock tested on Windows.
type switchLock struct{}

func takeSwitchLock(releaseDisk, string, []string) (switchLock, error) {
	return switchLock{}, fmt.Errorf("locking the switch: %w", errors.ErrUnsupported)
}

func (switchLock) release() {}
