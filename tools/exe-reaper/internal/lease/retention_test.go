package lease

import (
	"slices"
	"testing"
	"time"
)

// DecideRetention is L1's retention step: which tasks the TTL deletes, which
// images get L1's `inuse-` tag, and which tags go. exe/spec/retention.qnt is
// its model; these tables pin each rule, and TestSimulationRetention runs it
// against the model's environment.

const (
	digestA = "sha256:aaaaaaaaaaaa1111111111111111111111111111111111111111111111111111"
	digestB = "sha256:bbbbbbbbbbbb2222222222222222222222222222222222222222222222222222"
	pkgTask = "exe-task/task"
)

var (
	imageA = Image{Package: pkgTask, Digest: digestA}
	imageB = Image{Package: pkgTask, Digest: digestB}
)

func retentionBase() RetentionObservation {
	return RetentionObservation{Now: ref()}
}

func TestTagNames(t *testing.T) {
	if got := L1TagName(digestA); got != "inuse-aaaaaaaaaaaa" {
		t.Errorf("L1TagName = %q", got)
	}
	at := time.Date(2026, 9, 28, 0, 0, 0, 0, time.UTC)
	if got := JobTagName(digestA, at); got != "inuse-aaaaaaaaaaaa-1790553600" {
		t.Errorf("JobTagName = %q", got)
	}

	tests := []struct {
		name     string
		kind     tagKind
		stamp    time.Time
		forImage string
	}{
		{"inuse-aaaaaaaaaaaa", tagL1, time.Time{}, digestA},
		{"inuse-aaaaaaaaaaaa-1790553600", tagJob, at, digestA},
		{"inuse-aaaaaaaaaaaa", tagOther, time.Time{}, digestB},            // names another digest
		{"inuse-aaaaaaaaaaaa-1790553600", tagOther, time.Time{}, digestB}, // names another digest
		{"inuse-keep-forever", tagOther, time.Time{}, digestA},            // someone else's
		{"inuse-aaaaaaaaaaaa-x", tagOther, time.Time{}, digestA},
		{"latest", tagOther, time.Time{}, digestA},
	}
	for _, tc := range tests {
		kind, stamp := classifyTag(Tag{Name: tc.name, Image: Image{Package: pkgTask, Digest: tc.forImage}})
		if kind != tc.kind || !stamp.Equal(tc.stamp) {
			t.Errorf("%s on %s: %v %s, want %v %s", tc.name, tc.forImage[:14], kind, stamp, tc.kind, tc.stamp)
		}
	}
}

func TestTheTtlDeletesOnlyATaskSuspendedAndUnchangedForThirtyDays(t *testing.T) {
	now := ref()
	tests := []struct {
		name   string
		task   TaskObs
		keep   []string
		delete bool
	}{
		{"suspended and unchanged for exactly the TTL", TaskObs{Key: "exe/p1", Suspended: true, ChangedAt: now.Add(-TaskTTL)}, nil, true},
		{"one second short of the TTL", TaskObs{Key: "exe/p1", Suspended: true, ChangedAt: now.Add(-TaskTTL + time.Second)}, nil, false},
		{"running, however old", TaskObs{Key: "exe/p1", Suspended: false, ChangedAt: now.Add(-3 * TaskTTL)}, nil, false},
		{"kept by its full key", TaskObs{Key: "exe/p1", Suspended: true, ChangedAt: now.Add(-3 * TaskTTL)}, []string{"exe/p1"}, false},
		{"kept by its bare name", TaskObs{Key: "exe/p1", Suspended: true, ChangedAt: now.Add(-3 * TaskTTL)}, []string{"p1"}, false},
		{"a keep for another atespace does not keep it", TaskObs{Key: "exe/p1", Suspended: true, ChangedAt: now.Add(-3 * TaskTTL)}, []string{"other/p1"}, true},
		{"no update time at all: nothing proves its age", TaskObs{Key: "exe/p1", Suspended: true}, nil, false},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			o := retentionBase()
			o.Tasks = []TaskObs{tc.task}
			o.Keep = tc.keep
			d := DecideRetention(o)
			if got := slices.Contains(d.Delete, "exe/p1"); got != tc.delete {
				t.Errorf("delete = %t, want %t", got, tc.delete)
			}
		})
	}
}

func TestEveryImageALiveTaskOrTheClusterUsesGetsL1sTag(t *testing.T) {
	o := retentionBase()
	o.Tasks = []TaskObs{
		{Key: "exe/p1", Image: imageA},
		{Key: "exe/p2", Image: imageA}, // shared: tagged once
		{Key: "exe/p3"},                // not our image: nothing to tag
	}
	o.Platform = []Image{{Package: "exe-platform/exe-reap", Digest: digestB}}
	o.Tags = []Tag{{Name: L1TagName(digestB), Image: Image{Package: "exe-platform/exe-reap", Digest: digestB}}} // already tagged

	d := DecideRetention(o)
	if !slices.Equal(d.Tag, []Image{imageA}) {
		t.Errorf("tag %v, want exactly %v", d.Tag, imageA)
	}
	if len(d.Untag) != 0 {
		t.Errorf("untagged %v while everything is in use", d.Untag)
	}
}

func TestL1ReleasesItsTagOnlyAfterTheImageWasUnreferencedForTagRelease(t *testing.T) {
	// given L1's tag on an image nothing uses any more
	o := retentionBase()
	o.Tags = []Tag{{Name: L1TagName(digestA), Image: imageA}}

	// the first tick that sees it unreferenced starts the clock, and keeps it
	first := DecideRetention(o)
	if len(first.Untag) != 0 || !first.Record.Unreferenced[imageA.Key()].Equal(o.Now) {
		t.Fatalf("first sight: untag %v, record %v", first.Untag, first.Record.Unreferenced)
	}

	// one second short of TagRelease it still keeps it
	o.Record.Unreferenced = map[string]time.Time{imageA.Key(): o.Now.Add(-TagRelease + time.Second)}
	if d := DecideRetention(o); len(d.Untag) != 0 {
		t.Errorf("released %v before TagRelease", d.Untag)
	}

	// at TagRelease it goes, and so does the record
	o.Record.Unreferenced = map[string]time.Time{imageA.Key(): o.Now.Add(-TagRelease)}
	d := DecideRetention(o)
	if !slices.Equal(d.Untag, []Tag{{Name: L1TagName(digestA), Image: imageA}}) {
		t.Errorf("untag %v, want L1's tag on A", d.Untag)
	}
	if _, still := d.Record.Unreferenced[imageA.Key()]; still {
		t.Error("a released image is still in the record")
	}

	// and an image used again forgets its clock
	o.Tasks = []TaskObs{{Key: "exe/p1", Image: imageA}}
	if d := DecideRetention(o); len(d.Untag) != 0 || len(d.Record.Unreferenced) != 0 {
		t.Errorf("an image in use again: untag %v, record %v", d.Untag, d.Record.Unreferenced)
	}
}

func TestAxJobsTagGoesByTheDateInItsNameAndNeverByARecord(t *testing.T) {
	// The finding retention.qnt's sharedJobTag keeps: L1's record for an image
	// can be weeks old, so ax-job's tag must not be judged by it.
	o := retentionBase()
	o.Record.Unreferenced = map[string]time.Time{imageA.Key(): o.Now.Add(-10 * TagRelease)}
	fresh := Tag{Name: JobTagName(digestA, o.Now.Add(-time.Minute)), Image: imageA}
	old := Tag{Name: JobTagName(digestA, o.Now.Add(-TagRelease)), Image: imageA}
	o.Tags = []Tag{fresh, old}

	d := DecideRetention(o)
	if !slices.Equal(d.Untag, []Tag{old}) {
		t.Errorf("untag %v, want only the one dated TagRelease ago", d.Untag)
	}
}

func TestATagL1DoesNotRecogniseIsNeverTouched(t *testing.T) {
	o := retentionBase()
	o.Record.Unreferenced = map[string]time.Time{imageA.Key(): o.Now.Add(-10 * TagRelease)}
	o.Tags = []Tag{
		{Name: "inuse-keep-forever", Image: imageA},
		{Name: L1TagName(digestB), Image: imageA}, // its sha12 names another digest
	}
	if d := DecideRetention(o); len(d.Untag) != 0 {
		t.Errorf("untagged %v", d.Untag)
	}
}

func TestATaskDeletedByTheTtlReleasesItsImageOnTheUsualClock(t *testing.T) {
	o := retentionBase()
	o.Tasks = []TaskObs{{Key: "exe/p1", Image: imageA, Suspended: true, ChangedAt: o.Now.Add(-TaskTTL)}}
	o.Tags = []Tag{{Name: L1TagName(digestA), Image: imageA}}

	d := DecideRetention(o)
	if !slices.Equal(d.Delete, []string{"exe/p1"}) {
		t.Fatalf("delete %v", d.Delete)
	}
	// its image is unreferenced from now, and keeps its tag until TagRelease
	if len(d.Untag) != 0 || !d.Record.Unreferenced[imageA.Key()].Equal(o.Now) {
		t.Errorf("untag %v, record %v", d.Untag, d.Record.Unreferenced)
	}
}

func TestTheRecordTellsExeStatusWhenEachTaskIsDue(t *testing.T) {
	now := ref()
	o := retentionBase()
	o.Tasks = []TaskObs{
		{Key: "exe/p2", Image: imageB, Suspended: true, ChangedAt: now.Add(-24 * time.Hour)},
		{Key: "exe/p1", Image: imageA},
		{Key: "exe/p3", Suspended: true, ChangedAt: now.Add(-48 * time.Hour)},
	}
	o.Keep = []string{"p3"}

	d := DecideRetention(o)
	want := []TaskRecord{
		{Task: "exe/p1", Image: imageA.Key()},
		{Task: "exe/p2", Image: imageB.Key(), Suspended: true, DeleteAt: now.Add(-24 * time.Hour).Add(TaskTTL)},
		{Task: "exe/p3", Suspended: true, Kept: true},
	}
	if !slices.Equal(d.Record.Tasks, want) {
		t.Errorf("record tasks:\n got %+v\nwant %+v", d.Record.Tasks, want)
	}
	if !d.Record.At.Equal(now) {
		t.Errorf("record at %s, want %s", d.Record.At, now)
	}
}
