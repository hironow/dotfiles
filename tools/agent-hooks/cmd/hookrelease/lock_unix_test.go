//go:build unix

package main

import (
	"errors"
	"io"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"testing"
)

func TestLockStartsAgainWhenReleasesGoesBeforeItOpens(t *testing.T) {
	// given a releases directory, in a parent this build creates, that a
	// failed first build removes after this build has made sure it is
	// there, and before it opens it
	parent := filepath.Join(t.TempDir(), "new")
	releases := filepath.Join(parent, "releases")
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
	if !removed {
		lock.release()
		t.Fatal("the directory was not removed before the open")
	}
	if _, err := os.Stat(releases); err != nil {
		lock.release()
		t.Fatalf("the locked directory is not there: %v", err)
	}
	// when the build fails, then it leaves none of the directories it
	// created, in either attempt
	lock.release()
	if _, err := os.Stat(parent); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("a directory the build created remains: %v", err)
	}
}

func TestCreatedDirectoriesGoDeepestFirst(t *testing.T) {
	// A parent created in one attempt and its child in a later one: the
	// child must go first, or the parent is not empty when it is removed.
	got := deepestFirst([]string{"/d/new", "/d/new/releases", "/d/new/releases"})
	if want := []string{"/d/new/releases", "/d/new"}; !slices.Equal(got, want) {
		t.Fatalf("deepestFirst = %q, want %q", got, want)
	}
}

func TestLockGivesUpOnADirectoryThatKeepsGoing(t *testing.T) {
	// given a releases directory, in a parent this build creates, removed
	// before every open
	parent := filepath.Join(t.TempDir(), "new")
	releases := filepath.Join(parent, "releases")
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
	if _, err := os.Stat(parent); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("a directory the build created remains: %v", err)
	}
}
