package main_test

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logline"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logsink"
)

func writeLogDay(t *testing.T, state string, day time.Time, content []byte) {
	t.Helper()
	logs := filepath.Join(state, "dotfiles", "agent-hooks", "logs")
	if err := os.MkdirAll(logs, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(logs, day.Format("2006-01-02")+".jsonl"), content, 0o600); err != nil {
		t.Fatal(err)
	}
}

func usageLine(t *testing.T, now time.Time, harness string) []byte {
	t.Helper()
	line, err := logline.Build(logline.Firing{Usage: true, Harness: harness}, nil, now, [8]byte{}, [16]byte{}).Marshal()
	if err != nil {
		t.Fatal(err)
	}
	return line
}

func TestAgentHookLogKeepsAGoodDayAfterAPartialDay(t *testing.T) {
	skipOnWindows(t)
	state := t.TempDir()
	now := time.Now().UTC()
	writeLogDay(t, state, now.AddDate(0, 0, -1), []byte("{"))
	writeLogDay(t, state, now, usageLine(t, now, "claude"))

	exit, stdout, stderr := runIn(t, state, nil, "log", "--days", "2")
	if exit != 0 || stderr != "" || !strings.Contains(stdout, "claude") || !strings.Contains(stdout, "Skipped 1 unreadable lines.") {
		t.Fatalf("exit %d, stdout %q, stderr %q; want today's line and one skipped line", exit, stdout, stderr)
	}
}

func TestAgentHookLogSortsByTimeAndKeepsTiesInAppendOrder(t *testing.T) {
	skipOnWindows(t)
	state := t.TempDir()
	now := time.Now().UTC()
	first := time.Date(now.Year(), now.Month(), now.Day(), 1, 0, 0, 0, time.UTC)
	last := first.Add(time.Hour)
	content := usageLine(t, last, "claude")
	content = append(content, usageLine(t, first, "codex")...)
	content = append(content, usageLine(t, first, "pi")...)
	writeLogDay(t, state, now, content)

	exit, stdout, stderr := runIn(t, state, nil, "log")
	rows := strings.Split(strings.TrimSpace(stdout), "\n")
	if exit != 0 || stderr != "" || len(rows) != 4 {
		t.Fatalf("exit %d, stdout %q, stderr %q; want a header and three sorted rows", exit, stdout, stderr)
	}
	for i, harness := range []string{"codex", "pi", "claude"} {
		if fields := strings.Fields(rows[i+1]); len(fields) < 2 || fields[1] != harness {
			t.Errorf("row %d = %q; want %s in stable time order", i, rows[i+1], harness)
		}
	}
}

func TestAgentHookLogBoundsTheDayCount(t *testing.T) {
	skipOnWindows(t)
	for _, days := range []int{-1, 0, 1, logsink.KeepDays + 1, logsink.KeepDays + 2, 2000000000} {
		t.Run(strconv.Itoa(days), func(t *testing.T) {
			state := t.TempDir()
			exit, stdout, stderr := runIn(t, state, nil, "log", "--days", strconv.Itoa(days))
			if days >= 1 && days <= logsink.KeepDays+1 {
				if exit != 0 || !strings.Contains(stdout, "No log yet") || stderr != "" {
					t.Errorf("valid days %d: exit %d, stdout %q, stderr %q", days, exit, stdout, stderr)
				}
				return
			}
			if exit != 64 || stdout != "" || !strings.Contains(stderr, "usage: agent-hook log") {
				t.Errorf("invalid days %d: exit %d, stdout %q, stderr %q; want exit 64 and usage", days, exit, stdout, stderr)
			}
		})
	}
}
