package fake

import (
	"bytes"
	"sync"
	"time"
)

// LogSink keeps log lines and a configured salt in memory.
// Configure SaltBytes before calling its methods concurrently.
type LogSink struct {
	// SaltBytes is the salt returned by Salt; nil means no salt.
	SaltBytes []byte
	mu        sync.Mutex
	lines     []LogEntry
}

// LogEntry is a written line and the time passed with it.
type LogEntry struct {
	// Time is the firing's time.
	Time time.Time
	// Line holds the bytes passed to Write.
	Line []byte
}

// Salt returns an independent copy of the configured salt, or false for nil.
func (s *LogSink) Salt() ([]byte, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return bytes.Clone(s.SaltBytes), s.SaltBytes != nil
}

// Write keeps an independent copy of the line and its time.
func (s *LogSink) Write(now time.Time, line []byte) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.lines = append(s.lines, LogEntry{Time: now, Line: bytes.Clone(line)})
	return nil
}

// Lines returns independent copies of every entry, in write order.
func (s *LogSink) Lines() []LogEntry {
	s.mu.Lock()
	defer s.mu.Unlock()
	lines := make([]LogEntry, len(s.lines))
	for i, entry := range s.lines {
		lines[i] = LogEntry{Time: entry.Time, Line: bytes.Clone(entry.Line)}
	}
	return lines
}
