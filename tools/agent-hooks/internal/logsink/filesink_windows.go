//go:build windows

package logsink

import (
	"errors"
	"fmt"
	"time"
)

// FileSink is reserved for the Windows file log adapter.
type FileSink struct{}

// OpenFileSink reports that the file log is not on Windows yet.
func OpenFileSink(_ string, _ int) (*FileSink, error) {
	return nil, windowsFileLogError()
}

// Close releases no resources on Windows.
func (*FileSink) Close() error { return nil }

// Salt returns no salt on Windows.
func (*FileSink) Salt() ([]byte, bool) { return nil, false }

// Write reports that the file log is not on Windows yet.
func (*FileSink) Write(_ time.Time, _ []byte) error { return windowsFileLogError() }

// Read reports that the file log is not on Windows yet.
func (*FileSink) Read(_ time.Time, _ int) ([]byte, error) {
	return nil, windowsFileLogError()
}

func windowsFileLogError() error {
	return fmt.Errorf("file log is not on Windows yet: %w", errors.ErrUnsupported)
}
