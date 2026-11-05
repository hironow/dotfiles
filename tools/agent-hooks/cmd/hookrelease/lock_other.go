//go:build !unix

package main

import (
	"errors"
	"fmt"
	"io"
)

// releasesLock has no implementation here: build refuses Windows until its
// own PR, which brings a lock tested on Windows.
type releasesLock struct{}

func lockReleases(string, io.Writer) (releasesLock, error) {
	return releasesLock{}, fmt.Errorf("locking a releases directory: %w", errors.ErrUnsupported)
}

func (releasesLock) release() {}
