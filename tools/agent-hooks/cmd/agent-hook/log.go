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
	"slices"
	"strings"
	"sync"
	"time"

	json "github.com/goccy/go-json/v2"

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

// printLog is `agent-hook log [--days N] [--summary]`: the lines of the last
// N UTC days (today's included; default 1) as a table, oldest first, or with
// --summary their counts as one JSON object (logline.Summary) for doctor. A
// line it cannot read is skipped and counted. Reading makes nothing: with no
// log directory yet, it says so, or gives zero counts.
func printLog(args []string, stdout, stderr io.Writer, lookupEnv func(string) (string, bool), now time.Time) int {
	flags := flag.NewFlagSet("agent-hook log", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	days := flags.Int("days", 1, "how many UTC days to print, today's included")
	summary := flags.Bool("summary", false, "print the counts as JSON")
	if err := flags.Parse(args); err != nil || flags.NArg() > 0 || *days < 1 || *days > logsink.KeepDays+1 {
		_, _ = fmt.Fprintf(stderr, "usage: agent-hook log [--days N] [--summary], with N from 1 to %d\n", logsink.KeepDays+1)
		return exitUsage
	}
	if *summary && runtime.GOOS == "windows" {
		return printSummary(stdout, logline.Summarize(*days, nil, 0)) // no file log on Windows yet
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
		if *summary {
			return printSummary(stdout, logline.Summarize(*days, nil, 0))
		}
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
		if *summary {
			return printSummary(stdout, logline.Summarize(*days, nil, 0))
		}
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
	if *summary {
		return printSummary(stdout, logline.Summarize(*days, lines, skipped))
	}
	slices.SortStableFunc(lines, func(a, b logline.Line) int {
		return strings.Compare(a.Time, b.Time)
	})
	if _, err := io.WriteString(stdout, logline.Table(lines, skipped)); err != nil {
		return 1
	}
	return 0
}

// printSummary writes the summary as one line of JSON, its maps' keys sorted
// so the same log always gives the same bytes.
func printSummary(stdout io.Writer, summary logline.Summary) int {
	encoded, err := json.Marshal(summary, json.Deterministic(true))
	if err != nil {
		return 1
	}
	if _, err := stdout.Write(append(encoded, '\n')); err != nil {
		return 1
	}
	return 0
}
