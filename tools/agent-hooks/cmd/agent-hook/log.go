package main

import (
	"bytes"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"runtime"
	"sync"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logline"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logsink"
)

// exitUsage is the exit code of an argument the binary does not know
// (sysexits.h), as the hooks' runs use.
const exitUsage = 64

// fileLog is the log a run writes to: the FileSink under the state directory
// (logsink.Base), opened on first use. The run uses it only after the answer
// is written, within its logging deadline, so opening it never delays the
// answer. With no state directory, or on Windows (no file log yet), it logs
// nothing.
type fileLog struct {
	once sync.Once
	sink *logsink.FileSink
}

// errNoFileLog is a write with no file log to write to.
var errNoFileLog = errors.New("no file log")

func (f *fileLog) open() *logsink.FileSink {
	f.once.Do(func() {
		base, ok := logsink.Base(os.LookupEnv)
		if !ok {
			return
		}
		if sink, err := logsink.OpenFileSink(base, os.Getuid()); err == nil {
			f.sink = sink
		}
	})
	return f.sink
}

// Salt is the file log's salt, or none without a file log.
func (f *fileLog) Salt() ([]byte, bool) {
	if sink := f.open(); sink != nil {
		return sink.Salt()
	}
	return nil, false
}

// Write appends the line to the file log.
func (f *fileLog) Write(now time.Time, line []byte) error {
	sink := f.open()
	if sink == nil {
		return errNoFileLog
	}
	return sink.Write(now, line)
}

// printLog is `agent-hook log [--days N]`: the lines of the last N UTC days
// (today's included; default 1) as a table, oldest first. A line it cannot
// read is skipped and counted at the end. Reading makes nothing: with no log
// directory yet, it says so.
func printLog(args []string, stdout, stderr io.Writer, lookupEnv func(string) (string, bool), now time.Time) int {
	flags := flag.NewFlagSet("agent-hook log", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	days := flags.Int("days", 1, "how many UTC days to print, today's included")
	if err := flags.Parse(args); err != nil || flags.NArg() > 0 || *days < 1 {
		_, _ = fmt.Fprintln(stderr, "usage: agent-hook log [--days N], with N at least 1")
		return exitUsage
	}
	base, ok := logsink.Base(lookupEnv)
	if !ok {
		_, _ = fmt.Fprintln(stderr, "agent-hook log: no state directory: XDG_STATE_HOME or HOME must be an absolute path")
		return 1
	}
	// OpenFileSink makes what is missing; a reader should not. (On Windows it
	// makes nothing: it only says that there is no file log there yet.)
	logs := filepath.Join(base, "dotfiles", "agent-hooks", "logs")
	if _, err := os.Lstat(logs); runtime.GOOS != "windows" && errors.Is(err, fs.ErrNotExist) {
		_, _ = fmt.Fprintln(stdout, "No log yet: no hook run has written one.")
		return 0
	}
	sink, err := logsink.OpenFileSink(base, os.Getuid())
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "agent-hook log: %v\n", err)
		return 1
	}
	defer sink.Close()
	data, err := sink.Read(now, *days)
	if err != nil {
		_, _ = fmt.Fprintf(stderr, "agent-hook log: %v\n", err)
		return 1
	}
	if len(data) == 0 {
		_, _ = fmt.Fprintf(stdout, "No log lines in the last %d UTC day(s).\n", *days)
		return 0
	}
	var lines []logline.Line
	skipped := 0
	for text := range bytes.Lines(data) {
		line, err := logline.Parse(text)
		if err != nil {
			skipped++
			continue
		}
		lines = append(lines, line)
	}
	if _, err := io.WriteString(stdout, logline.Table(lines, skipped)); err != nil {
		return 1
	}
	return 0
}
