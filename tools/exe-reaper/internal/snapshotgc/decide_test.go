package snapshotgc

import (
	"slices"
	"strings"
	"testing"
	"time"
)

// The orphan-snapshot GC's decision (Phase 6 plan D11). Substrate deletes the
// snapshots of the actors it deletes; what it cannot collect are the prefixes
// of actors a lost store forgot. A prefix is taken only when every condition
// holds, and each test below breaks one.

var now = time.Date(2026, 9, 28, 12, 0, 0, 0, time.UTC)

// The four prefixes Substrate v0.1.0 left behind (reports/phase-4.md), and
// UIDs for the actors, tasks and templates of the store that replaced it.
const (
	oldGolden1 = "6ae88be1-35d9-48c2-985a-2f4537984b68"
	oldGolden2 = "685de9fd-7f25-413f-bc19-57166865aa46"
	oldTask1   = "e6eb6f07-db76-4d15-82be-6b9c98b5121d"
	oldTask2   = "bd79d855-82b8-4dad-aa63-4dbf40901b5e"

	liveTask   = "0b9e2f4a-3c1d-4e5f-8a7b-9c0d1e2f3a4b"
	liveGolden = "1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f"
	goneGolden = "2d3e4f5a-6b7c-4d8e-9f0a-1b2c3d4e5f6a"
	lostTask   = "3e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b"
)

func prefix(atespace, uid string) string { return "ax/atespaces/" + atespace + "/actors/" + uid + "/" }

// object is one snapshot object under the prefix, last written age ago.
func object(atespace, uid, rest string, age time.Duration) Object {
	return Object{Name: prefix(atespace, uid) + rest, Updated: now.Add(-age), Generation: 1}
}

const month = 30 * 24 * time.Hour

func observe(objects ...Object) Observation {
	return Observation{Now: now, Bucket: "zz-snap", Root: "ax/", Objects: objects}
}

func paths(ps []Prefix) []string {
	var out []string
	for _, p := range ps {
		out = append(out, p.Path)
	}
	return out
}

// kept is the reason a prefix was kept, or "" if it was not.
func kept(d Decision, path string) string {
	for _, k := range d.Kept {
		if k.Prefix.Path == path {
			return k.Reason
		}
	}
	return ""
}

func TestAPrefixNoActorOwnsIsACandidateWithEveryObjectInIt(t *testing.T) {
	// given an old prefix nothing in the store knows, next to a live actor's
	o := observe(
		object("exe", oldTask1, "snapshots/s1/manifest", month),
		object("exe", oldTask1, "snapshots/s1/durable-dir/0", month+time.Hour),
		object("exe", liveTask, "snapshots/s9/manifest", month),
	)
	o.ActorUIDs = []string{liveTask}

	// when
	d := Decide(o)
	// then the orphan is a candidate, with both of its objects to delete
	if d.Refusal != "" {
		t.Fatalf("refused: %s", d.Refusal)
	}
	if got, want := paths(d.Candidates), []string{prefix("exe", oldTask1)}; !slices.Equal(got, want) {
		t.Fatalf("candidates %q, want %q", got, want)
	}
	if n := len(d.Candidates[0].Objects); n != 2 {
		t.Errorf("%d objects in the candidate, want 2", n)
	}
	// and the live actor's prefix is kept, saying why
	if kept(d, prefix("exe", liveTask)) == "" {
		t.Error("the prefix of an actor the store has was not kept")
	}
}

// Resume reads a template's golden snapshot from the prefix of the golden
// actor that took it (workflow_resume.go:182), and that actor may be long
// gone. The template alone holds the prefix.
func TestAPrefixASurvivingTemplatePointsIntoIsKept(t *testing.T) {
	o := observe(object("ate-golden", goneGolden, "snapshots/g1/manifest", month))
	o.ActorUIDs = []string{liveTask}
	o.URIs = []string{"gs://zz-snap/ax/atespaces/ate-golden/actors/" + goneGolden + "/snapshots/g1"}

	d := Decide(o)
	if len(d.Candidates) != 0 {
		t.Errorf("candidates %q: a template's golden snapshot would be deleted", paths(d.Candidates))
	}
	if !strings.Contains(kept(d, prefix("ate-golden", goneGolden)), "g1") {
		t.Errorf("kept for %q; want the URI that holds it", kept(d, prefix("ate-golden", goneGolden)))
	}
}

// ListActors and GetActor are two reads, and a task's actor seen by one is
// kept even when the other missed it.
func TestATasksActorIsKeptEvenWhenTheListMissedIt(t *testing.T) {
	o := observe(object("exe", liveTask, "snapshots/s1/manifest", month))
	o.ActorUIDs = []string{liveGolden}
	o.Tasks = []Task{{Key: "exe/t1", UID: liveTask}}

	d := Decide(o)
	if len(d.Candidates) != 0 {
		t.Errorf("candidates %q: a task's own snapshot would be deleted", paths(d.Candidates))
	}
	if !strings.Contains(kept(d, prefix("exe", liveTask)), "exe/t1") {
		t.Errorf("kept for %q; want the task named", kept(d, prefix("exe", liveTask)))
	}
}

func TestAPrefixWrittenInTheLastDayIsKept(t *testing.T) {
	// given an orphan-looking prefix whose newest object is 23 h old
	o := observe(
		object("exe", oldTask1, "snapshots/s1/manifest", month),
		object("exe", oldTask1, "snapshots/s2/manifest", 23*time.Hour),
	)
	o.ActorUIDs = []string{liveTask}

	d := Decide(o)
	if len(d.Candidates) != 0 {
		t.Errorf("candidates %q: a prefix written 23 h ago would be deleted", paths(d.Candidates))
	}
	if kept(d, prefix("exe", oldTask1)) == "" {
		t.Error("the fresh prefix was not reported as kept")
	}
}

// A task whose actor row the store lost points at a prefix nobody can name:
// AX keeps only the actor's name, and the UID in the path is gone with the
// row. So nothing in that task's atespace is taken, unless the operator names
// the prefix.
func TestATaskWithoutAnActorHoldsItsAtespaceUntilThePrefixIsNamed(t *testing.T) {
	o := observe(
		object("exe", lostTask, "snapshots/s1/manifest", month),
		object("ate-golden", oldGolden1, "snapshots/g/manifest", month),
	)
	o.ActorUIDs = []string{liveTask}
	o.Tasks = []Task{{Key: "exe/t2", Missing: true}}

	d := Decide(o)
	if got, want := paths(d.Candidates), []string{prefix("ate-golden", oldGolden1)}; !slices.Equal(got, want) {
		t.Errorf("candidates %q, want only the other atespace's %q", got, want)
	}
	if reason := kept(d, prefix("exe", lostTask)); !strings.Contains(reason, "exe/t2") || !strings.Contains(reason, "-allow") {
		t.Errorf("kept for %q; want the task named and -allow offered", reason)
	}
	if !slices.Equal(d.MissingActors, []string{"exe/t2"}) {
		t.Errorf("missing actors %q, want [exe/t2]", d.MissingActors)
	}

	// when the operator names that prefix
	o.Allow = []string{prefix("exe", lostTask)}
	d = Decide(o)
	// then it is a candidate too
	if got := paths(d.Candidates); !slices.Contains(got, prefix("exe", lostTask)) {
		t.Errorf("candidates %q: the named prefix was not taken", got)
	}
}

// -allow answers "which prefix was the lost task's" and nothing else: it
// never takes a prefix another condition holds.
func TestAllowNeverOverridesAnotherHold(t *testing.T) {
	o := observe(
		object("exe", liveTask, "snapshots/s1/manifest", month),
		object("exe", oldTask1, "snapshots/s1/manifest", time.Hour),
	)
	o.ActorUIDs = []string{liveTask}
	o.Tasks = []Task{{Key: "exe/t2", Missing: true}}
	o.Allow = []string{prefix("exe", liveTask), prefix("exe", oldTask1)}

	d := Decide(o)
	if len(d.Candidates) != 0 {
		t.Errorf("candidates %q: -allow overrode a live actor or a fresh write", paths(d.Candidates))
	}
}

func TestAnAllowThatNamesNoPrefixRefusesEverything(t *testing.T) {
	// A typo in -allow is the operator believing something is about to be
	// deleted that is not; better to stop than to half-do it.
	o := observe(object("exe", oldTask1, "snapshots/s1/manifest", month))
	o.ActorUIDs = []string{liveTask}
	o.Allow = []string{prefix("exe", "typo")}

	d := Decide(o)
	if d.Refusal == "" || len(d.Candidates) != 0 {
		t.Errorf("refusal %q, candidates %q: want a refusal and nothing to delete", d.Refusal, paths(d.Candidates))
	}
}

// An empty store next to a prefix written today is what a store that just
// lost its rows looks like, not a store with nothing in it.
func TestAnEmptyStoreBesideAFreshPrefixRefusesEverything(t *testing.T) {
	o := observe(
		object("exe", oldTask1, "snapshots/s1/manifest", month),
		object("exe", oldTask2, "snapshots/s1/manifest", time.Hour),
	)

	d := Decide(o)
	if d.Refusal == "" || len(d.Candidates) != 0 {
		t.Errorf("refusal %q, candidates %q: want a refusal and nothing to delete", d.Refusal, paths(d.Candidates))
	}
}

func TestAnEmptyStoreWithOnlyOldPrefixesMayLetThemGo(t *testing.T) {
	// The store swap the GC exists for: nothing in it, and every prefix a
	// month old.
	o := observe(
		object("exe", oldTask1, "snapshots/s1/manifest", month),
		object("exe", oldTask2, "snapshots/s1/manifest", month),
	)

	d := Decide(o)
	if d.Refusal != "" {
		t.Fatalf("refused: %s", d.Refusal)
	}
	if got, want := paths(d.Candidates), []string{prefix("exe", oldTask2), prefix("exe", oldTask1)}; !slices.Equal(got, want) {
		t.Errorf("candidates %q, want %q (in path order)", got, want)
	}
}

func TestOnlyActorPrefixesAreEverCandidates(t *testing.T) {
	// given old objects everywhere except under an actor's UID: a tag's
	// snapshot, a path that is not a UID, other trees, and the gVisor mirror
	o := observe(
		Object{Name: "ax/atespaces/exe/tags/" + oldTask1 + "/manifest", Updated: now.Add(-month), Generation: 1},
		Object{Name: "ax/atespaces/exe/actors/not-a-uid/manifest", Updated: now.Add(-month), Generation: 1},
		Object{Name: "ax/atespaces/exe/actors/" + strings.ToUpper(oldTask1) + "/manifest", Updated: now.Add(-month), Generation: 1},
		Object{Name: "ax/atespaces/exe/other/x", Updated: now.Add(-month), Generation: 1},
		Object{Name: "ax/atespaces/exe/actors/" + oldTask2, Updated: now.Add(-month), Generation: 1},
		Object{Name: "ax/elsewhere/x", Updated: now.Add(-month), Generation: 1},
		Object{Name: "mirror/gvisor/gvisor.tar.zstd", Updated: now.Add(-month), Generation: 1},
	)
	o.ActorUIDs = []string{liveTask}

	d := Decide(o)
	if len(d.Candidates) != 0 {
		t.Errorf("candidates %q: only ax/atespaces/<a>/actors/<uid>/ may ever be taken", paths(d.Candidates))
	}
}

func TestAStoreURIThisGCCannotReadRefusesEverything(t *testing.T) {
	// The same bucket addressed some other way would hold a prefix without
	// the GC seeing it.
	o := observe(object("exe", oldTask1, "snapshots/s1/manifest", month))
	o.ActorUIDs = []string{liveTask}
	o.URIs = []string{"https://storage.googleapis.com/zz-snap/ax/atespaces/exe/actors/" + oldTask1 + "/snapshots/s1"}

	d := Decide(o)
	if d.Refusal == "" || len(d.Candidates) != 0 {
		t.Errorf("refusal %q, candidates %q: want a refusal and nothing to delete", d.Refusal, paths(d.Candidates))
	}
}

func TestAURIInAnotherBucketHoldsNothingHere(t *testing.T) {
	o := observe(object("exe", oldTask1, "snapshots/s1/manifest", month))
	o.ActorUIDs = []string{liveTask}
	o.URIs = []string{"gs://elsewhere/ax/atespaces/exe/actors/" + oldTask1 + "/snapshots/s1"}

	d := Decide(o)
	if got := paths(d.Candidates); !slices.Equal(got, []string{prefix("exe", oldTask1)}) {
		t.Errorf("candidates %q: another bucket's URI held this bucket's prefix", got)
	}
}

// What 6.11 expects of the real bucket: on the store that replaced v0.1.0,
// with its actors, tasks and templates in place, exactly the four prefixes
// v0.1.0 left behind are taken.
func TestTheFourPrefixesSubstrateV010LeftBehindAreTheCandidates(t *testing.T) {
	o := observe(
		object("ate-golden", oldGolden1, "snapshots/g/manifest", 72*time.Hour),
		object("ate-golden", oldGolden2, "snapshots/g/manifest", 72*time.Hour),
		object("exe", oldTask1, "snapshots/s/manifest", 72*time.Hour),
		object("exe", oldTask2, "snapshots/s/manifest", 72*time.Hour),
		object("ate-golden", goneGolden, "snapshots/g2/manifest", 48*time.Hour),
		object("exe", liveTask, "snapshots/s/manifest", 2*time.Hour),
	)
	o.ActorUIDs = []string{liveTask, liveGolden}
	o.URIs = []string{"gs://zz-snap/ax/atespaces/ate-golden/actors/" + goneGolden + "/snapshots/g2"}
	o.Tasks = []Task{{Key: "exe/w1", UID: liveTask}}

	d := Decide(o)
	want := []string{
		prefix("ate-golden", oldGolden2),
		prefix("ate-golden", oldGolden1),
		prefix("exe", oldTask2),
		prefix("exe", oldTask1),
	}
	if got := paths(d.Candidates); !slices.Equal(got, want) {
		t.Errorf("candidates %q, want %q", got, want)
	}
	if n := len(d.Kept); n != 2 {
		t.Errorf("%d kept, want 2 (the template's and the live task's): %+v", n, d.Kept)
	}
}

func TestParseLocation(t *testing.T) {
	tests := []struct {
		in, bucket, root string
		ok               bool
	}{
		{"gs://zz-snap/ax/", "zz-snap", "ax/", true},
		{"gs://zz-snap/ax", "zz-snap", "ax/", true},
		{"gs://zz-snap/a/b/", "zz-snap", "a/b/", true},
		// the bucket root itself would put mirror/ under the GC's listing
		{"gs://zz-snap/", "", "", false},
		{"gs://zz-snap", "", "", false},
		{"s3://zz-snap/ax/", "", "", false},
		{"", "", "", false},
	}
	for _, tc := range tests {
		bucket, root, err := ParseLocation(tc.in)
		if bucket != tc.bucket || root != tc.root || (err == nil) != tc.ok {
			t.Errorf("ParseLocation(%q) = %q %q %v", tc.in, bucket, root, err)
		}
	}
}
