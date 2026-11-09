//go:build unix

package main

import (
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	json "github.com/goccy/go-json/v2"
)

// switchLockWait is how long a switch waits for another run's lock.
var switchLockWait = 30 * time.Second

// switchLock is the exclusive lock on <state>/dotfiles/agent-hooks/
// switch.lock that sync, uninstall, install, gc, and switch share. The
// system drops it when the process ends, killed or not.
type switchLock struct{ file *os.File }

// lockHolder is the one JSON line a holder writes into the lock file, so a
// run that waits can name it. Sync (scripts/agent_hook_wiring.py) writes the
// same line.
type lockHolder struct {
	PID     int      `json:"pid"`
	Argv    []string `json:"argv"`
	Started string   `json:"started"`
}

// takeSwitchLock takes the lock, waiting up to switchLockWait. Past that, it
// names the holder from its line and gives up.
func takeSwitchLock(disk releaseDisk, state string, argv []string) (switchLock, error) {
	if err := makeDirectories(disk, state, 0o700); err != nil {
		return switchLock{}, err
	}
	path := filepath.Join(state, "switch.lock")
	file, err := os.OpenFile(path, os.O_RDWR|os.O_CREATE, 0o600)
	if err != nil {
		return switchLock{}, err
	}
	deadline := time.Now().Add(switchLockWait)
	for {
		err := flock(file, syscall.LOCK_EX|syscall.LOCK_NB)
		if err == nil {
			break
		}
		if !errors.Is(err, syscall.EWOULDBLOCK) {
			file.Close()
			return switchLock{}, err
		}
		if !time.Now().Before(deadline) {
			holder, _ := io.ReadAll(io.NewSectionReader(file, 0, 4096))
			file.Close()
			return switchLock{}, fmt.Errorf("another run holds %s, waited %s: %s", path, switchLockWait, strings.TrimSpace(string(holder)))
		}
		time.Sleep(100 * time.Millisecond)
	}
	line, err := json.Marshal(lockHolder{PID: os.Getpid(), Argv: argv, Started: time.Now().UTC().Format(time.RFC3339)})
	if err == nil {
		err = file.Truncate(0)
	}
	if err == nil {
		_, err = file.WriteAt(append(line, '\n'), 0)
	}
	if err != nil {
		file.Close()
		return switchLock{}, err
	}
	return switchLock{file}, nil
}

func (l switchLock) release() { l.file.Close() }
