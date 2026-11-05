//go:build unix

package main

import (
	"cmp"
	"errors"
	"fmt"
	"io"
	"os"
	"slices"
	"syscall"
)

// releasesLock is a build's exclusive lock on its releases directory. The
// system drops it when the process ends, killed or not.
type releasesLock struct {
	dir     *os.File
	created []string
}

// testHookBeforeOpen runs between making sure the releases directory is
// there and opening it, so a test can remove it in that window.
var testHookBeforeOpen = func() {}

// lockReleases makes the releases directory and its parents if needed, and
// locks it (flock on the directory itself, so no lock file is left behind).
// It tells stderr when it waits for another build.
func lockReleases(releases string, stderr io.Writer) (releasesLock, error) {
	// Every directory this build created, in any attempt, deepest first:
	// what it removes when it fails, if they are still empty.
	var created []string
	fail := func(err error) (releasesLock, error) {
		removeEmptyDirectories(created)
		return releasesLock{}, err
	}
	for range 10 {
		made, err := makeReleaseParents(releases)
		created = deepestFirst(append(created, made...))
		if err != nil {
			return fail(err)
		}
		testHookBeforeOpen()
		dir, err := os.Open(releases)
		if errors.Is(err, os.ErrNotExist) {
			// A failed first build removed it between the two steps.
			continue
		}
		if err != nil {
			return fail(err)
		}
		if err := lockExclusive(dir, releases, stderr); err != nil {
			dir.Close()
			return fail(err)
		}
		// A failed first build removes the directory it made. A build that
		// waited on that directory then holds a lock on one that is gone,
		// and starts again.
		held, heldErr := dir.Stat()
		named, namedErr := os.Stat(releases)
		if heldErr == nil && namedErr == nil && os.SameFile(held, named) {
			return releasesLock{dir: dir, created: created}, nil
		}
		dir.Close()
	}
	return fail(fmt.Errorf("%s kept changing while this build waited for it", releases))
}

// deepestFirst orders directories of one path so that each comes before
// its parent, each once.
func deepestFirst(dirs []string) []string {
	slices.SortFunc(dirs, func(a, b string) int { return cmp.Compare(len(b), len(a)) })
	return slices.Compact(dirs)
}

func lockExclusive(dir *os.File, name string, stderr io.Writer) error {
	err := flock(dir, syscall.LOCK_EX|syscall.LOCK_NB)
	if errors.Is(err, syscall.EWOULDBLOCK) {
		fmt.Fprintf(stderr, "hookrelease: waiting for another build in %s\n", name)
		err = flock(dir, syscall.LOCK_EX)
	}
	return err
}

func flock(file *os.File, how int) error {
	for {
		err := syscall.Flock(int(file.Fd()), how)
		if !errors.Is(err, syscall.EINTR) {
			return err
		}
	}
}

// release removes the directories this build made if they are still empty
// (a failed first build leaves nothing), then unlocks.
func (l releasesLock) release() {
	removeEmptyDirectories(l.created)
	l.dir.Close()
}
