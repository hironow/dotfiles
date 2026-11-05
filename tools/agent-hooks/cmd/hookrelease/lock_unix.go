//go:build unix

package main

import (
	"errors"
	"fmt"
	"io"
	"os"
	"syscall"
)

// releasesLock is a build's exclusive lock on its releases directory. The
// system drops it when the process ends, killed or not.
type releasesLock struct {
	dir     *os.File
	created []string
}

// lockReleases makes the releases directory and its parents if needed, and
// locks it (flock on the directory itself, so no lock file is left behind).
// It tells stderr when it waits for another build.
func lockReleases(releases string, stderr io.Writer) (releasesLock, error) {
	for range 10 {
		created, err := makeReleaseParents(releases)
		if err != nil {
			return releasesLock{}, err
		}
		dir, err := os.Open(releases)
		if err != nil {
			removeEmptyDirectories(created)
			return releasesLock{}, err
		}
		if err := lockExclusive(dir, releases, stderr); err != nil {
			dir.Close()
			removeEmptyDirectories(created)
			return releasesLock{}, err
		}
		// A failed build removes the directory it made. A build that waited
		// on that directory then holds a lock on one that is gone, and tries
		// again.
		held, heldErr := dir.Stat()
		named, namedErr := os.Stat(releases)
		if heldErr == nil && namedErr == nil && os.SameFile(held, named) {
			return releasesLock{dir: dir, created: created}, nil
		}
		dir.Close()
	}
	return releasesLock{}, fmt.Errorf("%s kept changing while this build waited for it", releases)
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
