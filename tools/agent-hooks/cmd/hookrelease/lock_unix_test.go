//go:build unix

package main

import (
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLockStartsAgainWhenReleasesGoesBeforeItOpens(t *testing.T) {
	// given a releases directory that a failed first build removes after
	// this build has made sure it is there, and before it opens it
	releases := filepath.Join(t.TempDir(), "releases")
	removed := false
	testHookBeforeOpen = func() {
		if !removed {
			removed = true
			if err := os.Remove(releases); err != nil {
				t.Error(err)
			}
		}
	}
	t.Cleanup(func() { testHookBeforeOpen = func() {} })
	// when the build locks it
	lock, err := lockReleases(releases, io.Discard)
	// then it starts again, and holds a releases directory that is there
	if err != nil {
		t.Fatalf("lock after the directory went: %v", err)
	}
	defer lock.release()
	if !removed {
		t.Fatal("the directory was not removed before the open")
	}
	if _, err := os.Stat(releases); err != nil {
		t.Fatalf("the locked directory is not there: %v", err)
	}
}

func TestLockGivesUpOnADirectoryThatKeepsGoing(t *testing.T) {
	// given a releases directory removed before every open
	releases := filepath.Join(t.TempDir(), "releases")
	attempts := 0
	testHookBeforeOpen = func() {
		attempts++
		if err := os.Remove(releases); err != nil {
			t.Error(err)
		}
	}
	t.Cleanup(func() { testHookBeforeOpen = func() {} })
	// when a build locks it, then it gives up after its attempts and says why
	_, err := lockReleases(releases, io.Discard)
	if err == nil || !strings.Contains(err.Error(), "kept changing") || attempts != 10 {
		t.Fatalf("lock = %v after %d attempts, want it to give up after 10", err, attempts)
	}
}
