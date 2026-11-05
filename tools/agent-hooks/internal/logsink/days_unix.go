//go:build unix

package logsink

import (
	"errors"
	"io"
	"os"
	"strings"
	"time"
)

// Read concatenates the last days UTC day files, oldest first, skipping missing days.
// Every file is opened and checked through the saved logs handle.
func (s *FileSink) Read(now time.Time, days int) ([]byte, error) {
	var lines []byte
	for offset := days - 1; offset >= 0; offset-- {
		day := now.UTC().AddDate(0, 0, -offset)
		contents, err := s.readDay(day.Format("2006-01-02") + ".jsonl")
		if errors.Is(err, os.ErrNotExist) {
			continue
		}
		if err != nil {
			return nil, err
		}
		lines = append(lines, contents...)
		if len(contents) > 0 && contents[len(contents)-1] != '\n' {
			lines = append(lines, '\n')
		}
	}
	return lines, nil
}

func (s *FileSink) readDay(name string) ([]byte, error) {
	file, err := openFile(s.logs, name, os.O_RDONLY, s.uid, false)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	return io.ReadAll(file)
}

func (s *FileSink) retain(now time.Time) error {
	dir, err := s.logs.Open(".")
	if err != nil {
		return err
	}
	defer dir.Close()
	entries, err := dir.ReadDir(-1)
	if err != nil {
		return err
	}
	for _, entry := range entries {
		if entry.IsDir() || !expiredDay(entry.Name(), now) {
			continue
		}
		if err := removeIfPresent(s.logs, entry.Name()); err != nil {
			return err
		}
	}
	return nil
}

func expiredDay(name string, now time.Time) bool {
	if len(name) != len("2006-01-02.jsonl") || !strings.HasSuffix(name, ".jsonl") {
		return false
	}
	day, err := time.Parse("2006-01-02", strings.TrimSuffix(name, ".jsonl"))
	if err != nil {
		return false
	}
	today := now.UTC()
	cutoff := time.Date(today.Year(), today.Month(), today.Day(), 0, 0, 0, 0, time.UTC).AddDate(0, 0, -KeepDays)
	return day.Before(cutoff)
}
