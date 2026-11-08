package main

import (
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"strings"
	"testing"
)

// recordingDisk is the system's disk with each publish step recorded, by its
// path relative to the releases directory, and one step made to fail.
type recordingDisk struct {
	releases string
	steps    []string
	fail     string
}

func (d *recordingDisk) step(name string, paths []string, run func() error) error {
	parts := []string{name}
	for _, path := range paths {
		rel, err := filepath.Rel(d.releases, path)
		if err != nil {
			return err
		}
		parts = append(parts, filepath.ToSlash(rel))
	}
	step := strings.Join(parts, " ")
	d.steps = append(d.steps, step)
	if step == d.fail {
		return errors.New("injected failure: " + step)
	}
	return run()
}

func (d *recordingDisk) SyncFile(path string) error {
	return d.step("sync-file", []string{path}, func() error { return systemDisk{}.SyncFile(path) })
}

func (d *recordingDisk) SyncDirectory(path string) error {
	return d.step("sync-dir", []string{path}, func() error { return systemDisk{}.SyncDirectory(path) })
}

func (d *recordingDisk) Rename(oldpath, newpath string) error {
	return d.step("rename", []string{oldpath, newpath}, func() error { return systemDisk{}.Rename(oldpath, newpath) })
}

// unpublished is a releases directory holding one finished build, not yet
// published, and the plan that publishes it.
func unpublished(t *testing.T) (releasePlan, string, string) {
	t.Helper()
	releases := t.TempDir()
	tmp := filepath.Join(releases, ".tmp-1")
	if err := os.Mkdir(tmp, 0o755); err != nil {
		t.Fatal(err)
	}
	plan := releasePlan{target: buildTarget{OS: runtime.GOOS, Arch: runtime.GOARCH}, id: "0123456789abcdef"}
	mustWrite(t, filepath.Join(tmp, binaryName(plan.target)), []byte("release"))
	return plan, releases, tmp
}

func TestPublishSyncsBeforeAndAfterTheRename(t *testing.T) {
	// given a finished build in its temporary directory
	plan, releases, tmp := unpublished(t)
	disk := &recordingDisk{releases: releases}
	// when it is published
	path, err := plan.publish(disk, tmp, releases)
	if err != nil {
		t.Fatal(err)
	}
	// then the binary and its directory reach the disk before the rename
	// names them, and the rename reaches it after
	name := binaryName(plan.target)
	want := []string{
		"sync-file .tmp-1/" + name,
		"sync-dir .tmp-1",
		"rename .tmp-1 " + plan.id,
		"sync-dir .",
	}
	if !reflect.DeepEqual(disk.steps, want) {
		t.Fatalf("publish steps = %q, want %q", disk.steps, want)
	}
	if path != filepath.Join(releases, plan.id, name) || string(mustRead(t, path)) != "release" {
		t.Fatalf("published %q", path)
	}
}

func TestPublishFailureIsReported(t *testing.T) {
	name := binaryName(buildTarget{OS: runtime.GOOS})
	for _, tc := range []struct {
		fail      string
		published bool
	}{
		{"sync-file .tmp-1/" + name, false},
		{"sync-dir .tmp-1", false},
		{"rename .tmp-1 0123456789abcdef", false},
		// The release is in place, but the rename may not survive a power
		// loss; the next build finds the same bytes and accepts them.
		{"sync-dir .", true},
	} {
		t.Run(tc.fail, func(t *testing.T) {
			plan, releases, tmp := unpublished(t)
			disk := &recordingDisk{releases: releases, fail: tc.fail}
			if _, err := plan.publish(disk, tmp, releases); err == nil {
				t.Fatal("a failed step was not reported")
			}
			_, err := os.Lstat(filepath.Join(releases, plan.id))
			if published := err == nil; published != tc.published {
				t.Fatalf("release published = %v, want %v (%v)", published, tc.published, err)
			}
		})
	}
}
