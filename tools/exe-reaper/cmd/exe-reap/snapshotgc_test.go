package main

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"slices"
	"strings"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/ax"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/gcp"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/substrate"
)

// The snapshot-gc subcommand (plan D11) around snapshotgc.Decide: what it
// reads, in which order, and that it deletes only with -apply, only the
// candidates, and only as they were listed. The decision itself is tested in
// internal/snapshotgc.

const (
	gcBucket = "zz-snap"
	orphanA  = "e6eb6f07-db76-4d15-82be-6b9c98b5121d"
	orphanB  = "bd79d855-82b8-4dad-aa63-4dbf40901b5e"
	liveUID  = "0b9e2f4a-3c1d-4e5f-8a7b-9c0d1e2f3a4b"
)

var gcNow = time.Date(2026, 9, 28, 12, 0, 0, 0, time.UTC)

func gcPrefix(uid string) string { return "ax/atespaces/exe/actors/" + uid + "/" }

// gcWorld is the bucket, the store and AX, in memory, recording every call.
type gcWorld struct {
	calls []string

	objects   []gcp.Object
	listErr   error
	deleted   []string // "<name>@<generation>"
	deleteErr map[string]error

	refs    substrate.SnapshotRefs
	refsErr error
	uids    map[string]string // "<atespace>/<name>" -> UID; absent is ErrNoActor
	uidErr  error

	tasks    []ax.Task
	tasksErr error
}

func (w *gcWorld) ListObjects(_ context.Context, bucket, prefix string) ([]gcp.Object, error) {
	w.calls = append(w.calls, "gcs.List "+bucket+" "+prefix)
	return slices.Clone(w.objects), w.listErr
}

func (w *gcWorld) DeleteObject(_ context.Context, bucket, name string, generation int64) error {
	w.calls = append(w.calls, "gcs.Delete "+bucket+" "+name)
	if err := w.deleteErr[name]; err != nil {
		return err
	}
	w.deleted = append(w.deleted, fmt.Sprintf("%s@%d", name, generation))
	return nil
}

func (w *gcWorld) SnapshotRefs(context.Context) (substrate.SnapshotRefs, error) {
	w.calls = append(w.calls, "substrate.SnapshotRefs")
	return w.refs, w.refsErr
}

func (w *gcWorld) ActorUID(_ context.Context, atespace, name string) (string, error) {
	w.calls = append(w.calls, "substrate.ActorUID "+atespace+"/"+name)
	if w.uidErr != nil {
		return "", w.uidErr
	}
	uid, ok := w.uids[atespace+"/"+name]
	if !ok {
		return "", fmt.Errorf("%s/%s: %w", atespace, name, substrate.ErrNoActor)
	}
	return uid, nil
}

func (w *gcWorld) Tasks(context.Context) ([]ax.Task, error) {
	w.calls = append(w.calls, "ax.Tasks")
	return slices.Clone(w.tasks), w.tasksErr
}

// newGCWorld is a bucket with two orphaned prefixes a month old (two
// objects in A, one in B) and a live task's prefix.
func newGCWorld() *gcWorld {
	month := 30 * 24 * time.Hour
	return &gcWorld{
		objects: []gcp.Object{
			{Name: gcPrefix(orphanA) + "snapshots/s1/manifest", Updated: gcNow.Add(-month), Generation: 11},
			{Name: gcPrefix(orphanA) + "snapshots/s1/durable-dir/0", Updated: gcNow.Add(-month), Generation: 12},
			{Name: gcPrefix(orphanB) + "snapshots/s1/manifest", Updated: gcNow.Add(-month), Generation: 21},
			{Name: gcPrefix(liveUID) + "snapshots/s1/manifest", Updated: gcNow.Add(-time.Hour), Generation: 31},
		},
		refs:  substrate.SnapshotRefs{ActorUIDs: []string{liveUID}},
		uids:  map[string]string{"exe/w1": liveUID},
		tasks: []ax.Task{{Key: "exe/w1"}},
	}
}

func (w *gcWorld) gc(out *bytes.Buffer) *snapshotGC {
	return &snapshotGC{store: w, tasks: w, bucket: w, name: gcBucket, root: "ax/", out: out}
}

func TestSnapshotGCDryRunDeletesNothingAndSaysWhatItWouldTake(t *testing.T) {
	w := newGCWorld()
	var out bytes.Buffer

	if err := w.gc(&out).run(context.Background(), gcNow, false, nil); err != nil {
		t.Fatal(err)
	}
	if len(w.deleted) != 0 {
		t.Errorf("a dry run deleted %q", w.deleted)
	}
	for _, want := range []string{gcPrefix(orphanA), gcPrefix(orphanB), gcPrefix(liveUID), "dry run", "-apply"} {
		if !strings.Contains(out.String(), want) {
			t.Errorf("output does not mention %q:\n%s", want, out.String())
		}
	}
}

func TestSnapshotGCApplyDeletesExactlyTheCandidatesAsListed(t *testing.T) {
	w := newGCWorld()
	var out bytes.Buffer

	if err := w.gc(&out).run(context.Background(), gcNow, true, nil); err != nil {
		t.Fatal(err)
	}
	want := []string{
		gcPrefix(orphanB) + "snapshots/s1/manifest@21",
		gcPrefix(orphanA) + "snapshots/s1/manifest@11",
		gcPrefix(orphanA) + "snapshots/s1/durable-dir/0@12",
	}
	slices.Sort(want)
	got := slices.Sorted(slices.Values(w.deleted))
	if !slices.Equal(got, want) {
		t.Errorf("deleted %q, want %q", got, want)
	}
	if !strings.Contains(out.String(), "deleted") {
		t.Errorf("output does not report the deletes:\n%s", out.String())
	}
}

// The bucket is listed before the store is read. A prefix that appears after
// the listing is never among the objects; one written before it by an actor
// the store has since read is kept by that read. The other order would leave
// a window where neither holds.
func TestSnapshotGCListsTheBucketBeforeItReadsTheStore(t *testing.T) {
	w := newGCWorld()
	var out bytes.Buffer

	if err := w.gc(&out).run(context.Background(), gcNow, false, nil); err != nil {
		t.Fatal(err)
	}
	if len(w.calls) == 0 || w.calls[0] != "gcs.List "+gcBucket+" ax/atespaces/" {
		t.Errorf("calls %q: want the bucket listed first, under ax/atespaces/", w.calls)
	}
}

func TestSnapshotGCTakesATaskWhoseActorIsMissingAsMissing(t *testing.T) {
	// given a task whose actor row is gone: its atespace is held
	w := newGCWorld()
	w.tasks = append(w.tasks, ax.Task{Key: "exe/lost"})
	var out bytes.Buffer

	if err := w.gc(&out).run(context.Background(), gcNow, true, nil); err != nil {
		t.Fatal(err)
	}
	if len(w.deleted) != 0 {
		t.Errorf("deleted %q in an atespace with a task whose actor is missing", w.deleted)
	}
	if !strings.Contains(out.String(), "exe/lost") {
		t.Errorf("output does not name the task:\n%s", out.String())
	}

	// when the operator names one prefix
	var again bytes.Buffer
	if err := w.gc(&again).run(context.Background(), gcNow, true, []string{gcPrefix(orphanB)}); err != nil {
		t.Fatal(err)
	}
	// then only that prefix goes
	if want := []string{gcPrefix(orphanB) + "snapshots/s1/manifest@21"}; !slices.Equal(w.deleted, want) {
		t.Errorf("deleted %q, want %q", w.deleted, want)
	}
}

func TestSnapshotGCAFailedReadDeletesNothing(t *testing.T) {
	boom := errors.New("unavailable")
	for name, breakIt := range map[string]func(w *gcWorld){
		"the bucket":   func(w *gcWorld) { w.listErr = boom },
		"the store":    func(w *gcWorld) { w.refsErr = boom },
		"AX":           func(w *gcWorld) { w.tasksErr = boom },
		"a task actor": func(w *gcWorld) { w.uidErr = boom },
	} {
		t.Run(name, func(t *testing.T) {
			w := newGCWorld()
			breakIt(w)
			var out bytes.Buffer
			if err := w.gc(&out).run(context.Background(), gcNow, true, nil); err == nil {
				t.Error("a failed read reported success")
			}
			if len(w.deleted) != 0 {
				t.Errorf("deleted %q after a failed read of %s", w.deleted, name)
			}
		})
	}
}

func TestSnapshotGCRefusalDeletesNothingAndFails(t *testing.T) {
	// given an -allow that names no prefix
	w := newGCWorld()
	var out bytes.Buffer

	err := w.gc(&out).run(context.Background(), gcNow, true, []string{gcPrefix("typo")})
	if err == nil {
		t.Error("a refusal reported success")
	}
	if len(w.deleted) != 0 {
		t.Errorf("deleted %q after a refusal", w.deleted)
	}
}

// An object rewritten since it was listed means something is writing where
// the GC believed nothing lived: its view is wrong, and it stops.
func TestSnapshotGCStopsAtTheFirstRewrittenObject(t *testing.T) {
	w := newGCWorld()
	w.deleteErr = map[string]error{
		gcPrefix(orphanB) + "snapshots/s1/manifest": fmt.Errorf("x: %w", gcp.ErrPreconditionFailed),
	}
	var out bytes.Buffer

	err := w.gc(&out).run(context.Background(), gcNow, true, nil)
	if !errors.Is(err, gcp.ErrPreconditionFailed) {
		t.Errorf("err %v, want the rewrite reported", err)
	}
	if len(w.deleted) != 0 {
		t.Errorf("deleted %q after the rewrite; want the run stopped there", w.deleted)
	}
}

func TestSnapshotGCWithoutItsLocationIsRefused(t *testing.T) {
	t.Setenv(envSnapshotsLocation, "")
	var stdout, stderr bytes.Buffer
	if code := run([]string{"snapshot-gc"}, &stdout, &stderr); code != 2 {
		t.Errorf("exit %d, want 2", code)
	}
	if !strings.Contains(stderr.String(), envSnapshotsLocation) {
		t.Errorf("stderr %q does not name %s", stderr.String(), envSnapshotsLocation)
	}
}

func TestSnapshotGCRefusesAStrayArgument(t *testing.T) {
	t.Setenv(envSnapshotsLocation, "gs://zz-snap/ax/")
	var stdout, stderr bytes.Buffer
	if code := run([]string{"snapshot-gc", "apply"}, &stdout, &stderr); code != 2 {
		t.Errorf("exit %d, want 2: a word where -apply was meant must not run", code)
	}
}
