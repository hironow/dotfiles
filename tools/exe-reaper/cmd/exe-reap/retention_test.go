package main

import (
	"encoding/json"
	"fmt"
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/ax"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/lease"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/ops"
)

// The retention step of the tick (plan D10, exe/spec/retention.qnt): after
// the drain's part, on a live lease with no drain, L1 tags the images live
// tasks use, deletes tasks past their TTL, releases tags nothing needs, and
// records it in tasks.json. DecideRetention's rules are tested in
// internal/lease; these test what the tick reads and does.

const (
	testRepo = "projects/zz-p/locations/asia-northeast1/repositories/exe-task"
	testPkg  = testRepo + "/packages/task"
	digestA  = "sha256:aaaaaaaaaaaa1111111111111111111111111111111111111111111111111111"
	digestB  = "sha256:bbbbbbbbbbbb2222222222222222222222222222222222222222222222222222"
	refA     = "asia-northeast1-docker.pkg.dev/zz-p/exe-task/task:v1@" + digestA
)

// withTask adds an AX task and its actor, at rest or awake, last changed at
// changedAt.
func withTask(w *world, key, image string, state lease.ActorState, changedAt time.Time) {
	w.axTasks = append(w.axTasks, ax.Task{Key: key, Image: image})
	w.actors = append(w.actors, lease.ActorObs{UID: "uid-" + key, Task: key, State: state, ChangedAt: changedAt})
	w.packages[testRepo] = []string{testPkg}
}

func (w *world) tasksRecord(t *testing.T) lease.TasksRecord {
	t.Helper()
	var rec lease.TasksRecord
	o, ok := w.objects[ops.TasksObject]
	if !ok {
		return rec
	}
	if err := json.Unmarshal(o.body, &rec); err != nil {
		t.Fatal(err)
	}
	return rec
}

func TestRetentionTagsTheImageEveryLiveTaskUsesAndRecordsTheTasks(t *testing.T) {
	w := newWorld(t)
	live(w)
	withTask(w, "exe/p1", refA, lease.ActorAwake, t0.Add(-time.Hour))

	if _, err := tick(t, w, t0); err != nil {
		t.Fatal(err)
	}
	if want := []string{testPkg + " " + lease.L1TagName(digestA)}; !slices.Equal(w.tagged, want) {
		t.Errorf("tagged %v, want %v", w.tagged, want)
	}
	rec := w.tasksRecord(t)
	if len(rec.Tasks) != 1 || rec.Tasks[0].Task != "exe/p1" || rec.Tasks[0].Image != testPkg+"@"+digestA {
		t.Errorf("tasks.json %+v", rec.Tasks)
	}
}

func TestRetentionDeletesATaskPastItsTtlThroughAXUnlessKept(t *testing.T) {
	for _, kept := range []bool{false, true} {
		t.Run(fmt.Sprintf("kept=%t", kept), func(t *testing.T) {
			w := newWorld(t)
			live(w)
			withTask(w, "exe/old", refA, lease.ActorAtRest, t0.Add(-lease.TaskTTL))
			if kept {
				w.put(ops.KeepObject, ops.Keep{Tasks: []string{"old"}})
			}

			if _, err := tick(t, w, t0); err != nil {
				t.Fatal(err)
			}
			if got := slices.Contains(w.axDeleted, "exe/old"); got == kept {
				t.Errorf("deleted = %t with kept = %t", got, kept)
			}
		})
	}
}

func TestRetentionReleasesATagNothingHasUsedForTagRelease(t *testing.T) {
	w := newWorld(t)
	live(w)
	w.packages[testRepo] = []string{testPkg}
	w.tags[testPkg] = map[string]string{lease.L1TagName(digestB): digestB}
	w.put(ops.TasksObject, lease.TasksRecord{Unreferenced: map[string]time.Time{testPkg + "@" + digestB: t0.Add(-lease.TagRelease)}})

	if _, err := tick(t, w, t0); err != nil {
		t.Fatal(err)
	}
	if want := []string{testPkg + " " + lease.L1TagName(digestB)}; !slices.Equal(w.untagged, want) {
		t.Errorf("untagged %v, want %v", w.untagged, want)
	}
}

func TestRetentionLeavesImagesOutsideItsRepositoriesAlone(t *testing.T) {
	w := newWorld(t)
	live(w)
	withTask(w, "exe/p1", "asia-northeast1-docker.pkg.dev/zz-p/elsewhere/task@"+digestA, lease.ActorAwake, t0)
	withTask(w, "exe/p2", "ghcr.io/x/y:latest", lease.ActorAwake, t0)

	if _, err := tick(t, w, t0); err != nil {
		t.Fatal(err)
	}
	if len(w.tagged) != 0 {
		t.Errorf("tagged %v outside the managed repositories", w.tagged)
	}
}

func TestRetentionRunsOnlyOnALiveLeaseWithNoDrain(t *testing.T) {
	// A drain has the tick to itself: nothing about retention is urgent, and
	// a task deleted mid-drain is one more thing the drain has to watch.
	w := newWorld(t)
	expired(w)
	withTask(w, "exe/old", refA, lease.ActorAtRest, t0.Add(-lease.TaskTTL))

	if _, err := tick(t, w, t0); err != nil {
		t.Fatal(err)
	}
	for _, c := range w.calls {
		if strings.HasPrefix(c, "ax.Tasks") || strings.HasPrefix(c, "ar.") {
			t.Errorf("retention ran during a drain: %s", c)
		}
	}
}

func TestARetentionReadThatFailsFailsTheTickButNotTheDrainsPart(t *testing.T) {
	w := newWorld(t)
	live(w)
	withTask(w, "exe/p1", refA, lease.ActorAwake, t0)
	w.tasksErr = errBoom

	out, err := tick(t, w, t0)
	if err == nil {
		t.Fatal("a failed task list reported success")
	}
	// the drain's part of the tick stands: it decided, and said so
	if out.decision(t)["branch"] != string(lease.L1NoOp) {
		t.Errorf("the drain's part did not stand: %v", out.decision(t))
	}
	if len(w.tagged)+len(w.axDeleted) != 0 {
		t.Errorf("acted on a partial view: tagged %v, deleted %v", w.tagged, w.axDeleted)
	}
}

func TestTasksJSONIsWrittenOnlyWhenItChanges(t *testing.T) {
	w := newWorld(t)
	live(w)
	withTask(w, "exe/p1", refA, lease.ActorAwake, t0)

	if _, err := tick(t, w, t0); err != nil {
		t.Fatal(err)
	}
	w.puts = nil
	if _, err := tick(t, w, t0.Add(time.Minute)); err != nil {
		t.Fatal(err)
	}
	if slices.Contains(w.puts, ops.TasksObject) {
		t.Error("tasks.json was rewritten with nothing changed")
	}
}
