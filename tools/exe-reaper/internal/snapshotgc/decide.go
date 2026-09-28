// Package snapshotgc decides which snapshot prefixes the orphan-snapshot GC
// may delete (Phase 6 plan D11).
//
// Substrate collects the snapshots of the actors it deletes. What it cannot
// collect is the prefix of an actor a lost store forgot, and a store is lost
// only by an operator action: a teardown, or a store swap. So the GC is the
// operator's, dry-run unless told otherwise, and it takes a prefix only when
// every one of these holds:
//
//   - it is <root>atespaces/<atespace>/actors/<uid>/, with <uid> a UID as the
//     store writes them (a lowercase UUID);
//   - no actor in the store, in any atespace, ate-golden included, has that
//     UID;
//   - no snapshot URI the store points at lies inside it: an actor's
//     external snapshot, or a template's golden snapshot, which lives under
//     the golden actor that took it and outlives that actor;
//   - it is not the prefix of an AX task's actor, looked up by name;
//   - nothing in it was written in the last MinAge;
//   - no task in its atespace has lost its actor row, since the prefix of
//     such a task can no longer be told apart from an orphan's, unless the
//     operator names the prefix (Allow).
//
// It takes nothing at all when the store lists no actors beside a prefix
// written within MinAge (a store that just lost its rows looks exactly like
// that), when a URI cannot be read, or when an Allow names no prefix.
//
// The GC is not autonomous, so it has no retention invariant; this package's
// tests are its guard.
package snapshotgc

import (
	"fmt"
	"slices"
	"strings"
	"time"
)

// MinAge is how long a prefix must go unwritten before the GC may take it.
const MinAge = 24 * time.Hour

// Object is one object in the snapshot bucket, as listed.
type Object struct {
	Name       string
	Updated    time.Time
	Generation int64
}

// Task is one AX task and its actor, looked up by name.
type Task struct {
	// Key is "<atespace>/<name>".
	Key string
	// UID is the actor's UID. Empty when Missing.
	UID string
	// Missing is a task whose actor the store does not have.
	Missing bool
}

// Observation is everything the GC read, the bucket first.
type Observation struct {
	Now time.Time
	// Bucket and Root are the snapshot location the templates name
	// (gs://<Bucket>/<Root>), Root ending in "/".
	Bucket string
	Root   string
	// Objects is every object under <Root>atespaces/.
	Objects []Object
	// ActorUIDs is every actor in the store, in every atespace.
	ActorUIDs []string
	// URIs is every snapshot URI the store points at.
	URIs []string
	// Tasks is every AX task.
	Tasks []Task
	// Allow is the prefixes the operator named, in the form Prefix.Path.
	Allow []string
}

// Prefix is one actor's snapshots: every object under Path.
type Prefix struct {
	// Path is "<root>atespaces/<atespace>/actors/<uid>/".
	Path     string
	Atespace string
	UID      string
	// Objects is in name order.
	Objects []Object
	Newest  time.Time
}

// Kept is a prefix the GC leaves, and the first reason it does.
type Kept struct {
	Prefix Prefix
	Reason string
}

// Decision is what the GC may take. Candidates and Kept are in path order.
type Decision struct {
	// Refusal, when set, means take nothing at all; it says why.
	Refusal    string
	Candidates []Prefix
	Kept       []Kept
	// MissingActors is the tasks whose actor the store does not have.
	MissingActors []string
}

// Decide applies the rules in the package comment.
func Decide(o Observation) Decision {
	prefixes := group(o)
	d := Decision{}
	for _, t := range o.Tasks {
		if t.Missing {
			d.MissingActors = append(d.MissingActors, t.Key)
		}
	}
	slices.Sort(d.MissingActors)

	if d.Refusal = refusal(o, prefixes); d.Refusal != "" {
		return d
	}
	h := newHolds(o)
	for _, p := range prefixes {
		if reason := h.reason(p, o.Now); reason != "" {
			d.Kept = append(d.Kept, Kept{Prefix: p, Reason: reason})
			continue
		}
		d.Candidates = append(d.Candidates, p)
	}
	return d
}

// ParseLocation splits a snapshot location, gs://<bucket>/<root>/, into its
// bucket and root. The root may not be empty: the bucket's own root would
// put every other tenant of the bucket under the GC's listing.
func ParseLocation(location string) (bucket, root string, err error) {
	rest, ok := strings.CutPrefix(location, "gs://")
	if !ok {
		return "", "", fmt.Errorf("snapshot location %q is not gs://<bucket>/<root>/", location)
	}
	bucket, root, _ = strings.Cut(rest, "/")
	root = strings.TrimSuffix(root, "/")
	if bucket == "" || root == "" {
		return "", "", fmt.Errorf("snapshot location %q is not gs://<bucket>/<root>/", location)
	}
	return bucket, root + "/", nil
}

// group collects the objects under <root>atespaces/<atespace>/actors/<uid>/
// into one Prefix per actor, in path order. Every other object is ignored:
// tags' snapshots, the bucket's other tenants, and anything else.
func group(o Observation) []Prefix {
	base := o.Root + "atespaces/"
	byPath := map[string]*Prefix{}
	for _, obj := range o.Objects {
		rest, ok := strings.CutPrefix(obj.Name, base)
		if !ok {
			continue
		}
		parts := strings.SplitN(rest, "/", 4)
		if len(parts) < 4 || parts[0] == "" || parts[1] != "actors" || parts[2] == "" {
			continue
		}
		path := base + parts[0] + "/actors/" + parts[2] + "/"
		p, ok := byPath[path]
		if !ok {
			p = &Prefix{Path: path, Atespace: parts[0], UID: parts[2]}
			byPath[path] = p
		}
		p.Objects = append(p.Objects, obj)
		if obj.Updated.After(p.Newest) {
			p.Newest = obj.Updated
		}
	}
	out := make([]Prefix, 0, len(byPath))
	for _, p := range byPath {
		slices.SortFunc(p.Objects, func(a, b Object) int { return strings.Compare(a.Name, b.Name) })
		out = append(out, *p)
	}
	slices.SortFunc(out, func(a, b Prefix) int { return strings.Compare(a.Path, b.Path) })
	return out
}

// refusal is why the GC must take nothing at all, or "".
func refusal(o Observation, prefixes []Prefix) string {
	for _, uri := range o.URIs {
		if !strings.HasPrefix(uri, "gs://") {
			return fmt.Sprintf("the store points at %q, which is not a gs:// URI: a prefix it holds could not be seen", uri)
		}
	}
	for _, a := range o.Allow {
		if !slices.ContainsFunc(prefixes, func(p Prefix) bool { return p.Path == a }) {
			return fmt.Sprintf("-allow %s names no actor prefix under %satespaces/", a, o.Root)
		}
	}
	if len(o.ActorUIDs) == 0 {
		for _, p := range prefixes {
			if o.Now.Sub(p.Newest) < MinAge {
				return fmt.Sprintf("the store lists no actors, yet %s was written at %s: a store that just lost its rows looks exactly like this",
					p.Path, p.Newest.UTC().Format(time.RFC3339))
			}
		}
	}
	return ""
}

// holds is everything that keeps a prefix, indexed.
type holds struct {
	actors map[string]bool
	tasks  map[string]string   // actor UID -> task key
	lost   map[string][]string // atespace -> tasks whose actor is missing
	uris   []string            // URIs in this bucket, sorted
	allow  map[string]bool
	bucket string
}

func newHolds(o Observation) holds {
	h := holds{
		actors: map[string]bool{},
		tasks:  map[string]string{},
		lost:   map[string][]string{},
		allow:  map[string]bool{},
		bucket: "gs://" + o.Bucket + "/",
	}
	for _, uid := range o.ActorUIDs {
		h.actors[uid] = true
	}
	for _, t := range o.Tasks {
		if t.Missing {
			atespace, _, _ := strings.Cut(t.Key, "/")
			h.lost[atespace] = append(h.lost[atespace], t.Key)
			continue
		}
		h.tasks[t.UID] = t.Key
	}
	for _, lost := range h.lost {
		slices.Sort(lost)
	}
	for _, uri := range o.URIs {
		if strings.HasPrefix(uri, h.bucket) {
			h.uris = append(h.uris, uri)
		}
	}
	slices.Sort(h.uris)
	for _, a := range o.Allow {
		h.allow[a] = true
	}
	return h
}

// reason is the first rule that keeps p, or "" if none does.
func (h holds) reason(p Prefix, now time.Time) string {
	if !isUID(p.UID) {
		return "not an actor UID as the store writes them"
	}
	if h.actors[p.UID] {
		return "the store has this actor"
	}
	if task, ok := h.tasks[p.UID]; ok {
		return "the actor of task " + task
	}
	for _, uri := range h.uris {
		if path := strings.TrimPrefix(uri, h.bucket); strings.HasPrefix(path+"/", p.Path) {
			return "the store points at " + path
		}
	}
	if age := now.Sub(p.Newest); age < MinAge {
		return fmt.Sprintf("written %s ago, within %s", age.Round(time.Minute), MinAge)
	}
	if lost := h.lost[p.Atespace]; len(lost) > 0 && !h.allow[p.Path] {
		return fmt.Sprintf("task(s) %s in atespace %s have no actor in the store, and their prefixes look like this one; name it with -allow to take it",
			strings.Join(lost, ", "), p.Atespace)
	}
	return ""
}

// isUID reports whether s is a UID as the store writes them: a lowercase,
// hyphenated UUID (uuid.NewString in Substrate's store).
func isUID(s string) bool {
	if len(s) != 36 {
		return false
	}
	for i, r := range s {
		switch i {
		case 8, 13, 18, 23:
			if r != '-' {
				return false
			}
		default:
			if (r < '0' || r > '9') && (r < 'a' || r > 'f') {
				return false
			}
		}
	}
	return true
}
