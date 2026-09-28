package lease

import (
	"regexp"
	"slices"
	"strconv"
	"strings"
	"time"
)

// Retention is the other thing L1 decides on its own (Phase 6 plan D10, as
// amended by exe/spec/retention.qnt): which tasks the TTL deletes, and which
// images keep an `inuse-` tag so Artifact Registry's cleanup cannot collect an
// image a live task will need at its next resume -- every wake is a fresh
// node, so a resume pulls the image again.
//
//	TTL      a task whose actor is SUSPENDED and whose store record has not
//	         changed for TaskTTL is deleted, unless keep.json names it. The
//	         store moves update_time on every write, so a resume and a
//	         re-suspend between two ticks still restart the clock.
//	L1 tags  every image a live task or the cluster itself references gets
//	         `inuse-<sha12>`; the tag goes once the image has been
//	         unreferenced for TagRelease by tasks.json's record.
//	ax-job   tags the image before it applies a task, `inuse-<sha12>-<unix>`.
//	         That tag goes once its name says it is TagRelease old, and never
//	         by a record: the record for an image being reused can be weeks
//	         old (retention.qnt's rejected sharedJobTag).
//
// A tag of any other shape, `inuse-` or not, is never touched.

// Image is one image version: the Artifact Registry package it lives in and
// its digest. The package is opaque here; the reaper's AR client knows its
// shape.
type Image struct {
	Package string
	Digest  string
}

// Key names the image in tasks.json.
func (i Image) Key() string { return i.Package + "@" + i.Digest }

// TaskObs is one AX task as retention sees it.
type TaskObs struct {
	// Key is "<atespace>/<name>".
	Key string
	// Image is the task's image, or zero when it is not in a repository L1
	// manages or is not pinned by digest: nothing L1 can protect.
	Image Image
	// Suspended: the task's actor is SUSPENDED in the store.
	Suspended bool
	// ChangedAt is the actor's update_time in the store.
	ChangedAt time.Time
}

// Tag is one tag in a repository L1 manages.
type Tag struct {
	Name  string
	Image Image
}

// TasksRecord is tasks.json: L1's retention memory between ticks, and what
// exe-status shows while the node sleeps. One writer, L1.
type TasksRecord struct {
	At    time.Time    `json:"at"`
	Tasks []TaskRecord `json:"tasks,omitempty"`
	// Unreferenced maps each image L1 tagged that nothing references any
	// more (by Image.Key) to the first tick that saw it so.
	Unreferenced map[string]time.Time `json:"unreferenced,omitempty"`
}

// TaskRecord is one task in tasks.json.
type TaskRecord struct {
	Task      string `json:"task"`
	Image     string `json:"image,omitempty"`
	Suspended bool   `json:"suspended,omitempty"`
	// DeleteAt is when the TTL expires for a suspended task that is not
	// kept: the first tick after it deletes the task.
	DeleteAt time.Time `json:"deleteAt,omitzero"`
	Kept     bool      `json:"kept,omitempty"`
}

// RetentionObservation is everything the retention step sees on one tick.
type RetentionObservation struct {
	Now   time.Time
	Tasks []TaskObs
	// Platform is every image the cluster's own workloads run: they are
	// referenced exactly like a task's.
	Platform []Image
	// Keep is keep.json: task keys, or bare names meaning any atespace.
	Keep   []string
	Tags   []Tag
	Record TasksRecord
}

// RetentionDecision is what one retention step does. Like L1Decision, every
// part is a target state, so a step repeated after a partial failure is
// harmless.
type RetentionDecision struct {
	Record TasksRecord
	// Delete lists the task keys whose TTL expired.
	Delete []string
	// Tag lists the images to give L1's own tag.
	Tag []Image
	// Untag lists the tags to remove.
	Untag []Tag
}

// DecideRetention is L1's retention judgement for one tick.
func DecideRetention(o RetentionObservation) RetentionDecision {
	d := RetentionDecision{Record: TasksRecord{At: o.Now}}

	referenced := map[string]Image{}
	for _, img := range o.Platform {
		referenced[img.Key()] = img
	}
	for _, task := range o.Tasks {
		kept := isKept(task.Key, o.Keep)
		if task.Suspended && !kept && !task.ChangedAt.IsZero() && !o.Now.Before(task.ChangedAt.Add(TaskTTL)) {
			d.Delete = append(d.Delete, task.Key)
			continue
		}
		rec := TaskRecord{Task: task.Key, Suspended: task.Suspended, Kept: kept}
		if task.Image != (Image{}) {
			rec.Image = task.Image.Key()
			referenced[rec.Image] = task.Image
		}
		if task.Suspended && !kept && !task.ChangedAt.IsZero() {
			rec.DeleteAt = task.ChangedAt.Add(TaskTTL)
		}
		d.Record.Tasks = append(d.Record.Tasks, rec)
	}

	l1Tagged := map[string]Tag{}
	for _, tag := range o.Tags {
		switch kind, stamp := classifyTag(tag); kind {
		case tagL1:
			l1Tagged[tag.Image.Key()] = tag
		case tagJob:
			if !o.Now.Before(stamp.Add(TagRelease)) {
				d.Untag = append(d.Untag, tag)
			}
		case tagOther:
		}
	}

	for key, img := range referenced {
		if _, ok := l1Tagged[key]; !ok {
			d.Tag = append(d.Tag, img)
		}
	}
	for key, tag := range l1Tagged {
		if _, ok := referenced[key]; ok {
			continue
		}
		since, ok := o.Record.Unreferenced[key]
		if !ok {
			since = o.Now
		}
		if !o.Now.Before(since.Add(TagRelease)) {
			d.Untag = append(d.Untag, tag)
			continue
		}
		if d.Record.Unreferenced == nil {
			d.Record.Unreferenced = map[string]time.Time{}
		}
		d.Record.Unreferenced[key] = since
	}

	slices.Sort(d.Delete)
	slices.SortFunc(d.Tag, func(a, b Image) int { return strings.Compare(a.Key(), b.Key()) })
	slices.SortFunc(d.Untag, func(a, b Tag) int {
		return strings.Compare(a.Image.Key()+" "+a.Name, b.Image.Key()+" "+b.Name)
	})
	slices.SortFunc(d.Record.Tasks, func(a, b TaskRecord) int { return strings.Compare(a.Task, b.Task) })
	return d
}

// isKept reports whether keep.json names the task: by its full key, or by its
// bare name, which means the task of that name in any atespace.
func isKept(key string, keep []string) bool {
	_, name, _ := strings.Cut(key, "/")
	for _, k := range keep {
		if k == key || (!strings.Contains(k, "/") && k == name) {
			return true
		}
	}
	return false
}

// L1TagName is L1's own tag for an image: `inuse-` and the digest's first 12
// hex characters.
func L1TagName(digest string) string {
	return "inuse-" + sha12(digest)
}

// JobTagName is ax-job's tag for an image, dated in its name: `inuse-`, the
// digest's first 12 hex characters, and the Unix time it was made.
func JobTagName(digest string, at time.Time) string {
	return L1TagName(digest) + "-" + strconv.FormatInt(at.Unix(), 10)
}

func sha12(digest string) string {
	hex := strings.TrimPrefix(digest, "sha256:")
	if len(hex) > 12 {
		hex = hex[:12]
	}
	return hex
}

type tagKind int

const (
	tagOther tagKind = iota
	tagL1
	tagJob
)

var tagShape = regexp.MustCompile(`^inuse-([0-9a-f]{12})(?:-([0-9]+))?$`)

// classifyTag says whose tag this is. A tag is L1's or ax-job's only if its
// shape is theirs AND its sha12 names the digest it is on; anything else is
// someone else's and is never touched.
func classifyTag(t Tag) (tagKind, time.Time) {
	m := tagShape.FindStringSubmatch(t.Name)
	if m == nil || m[1] != sha12(t.Image.Digest) {
		return tagOther, time.Time{}
	}
	if m[2] == "" {
		return tagL1, time.Time{}
	}
	unix, err := strconv.ParseInt(m[2], 10, 64)
	if err != nil {
		return tagOther, time.Time{}
	}
	return tagJob, time.Unix(unix, 0).UTC()
}
