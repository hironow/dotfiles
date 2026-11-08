//go:build windows

// Package osrand reads OS randomness without terminating the process on failure.
package osrand

import "crypto/rand"

// Read fills p with crypto/rand, which Go documents cannot fail on Windows.
func Read(p []byte) error {
	_, err := rand.Read(p)
	return err
}
