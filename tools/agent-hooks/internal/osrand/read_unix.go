//go:build unix

// Package osrand reads OS randomness without terminating the process on failure.
package osrand

import (
	"errors"
	"io"
	"os"
)

// Read fills p from /dev/urandom and returns any open, read, or close error.
func Read(p []byte) error {
	file, err := os.Open("/dev/urandom")
	if err != nil {
		return err
	}
	_, readErr := io.ReadFull(file, p)
	return errors.Join(readErr, file.Close())
}
