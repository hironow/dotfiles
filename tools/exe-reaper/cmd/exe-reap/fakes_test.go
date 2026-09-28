package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"slices"
	"strings"
	"sync"
	"testing"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/ax"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/gcp"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/k8s"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/lease"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/ops"
)

// The tick's world, in memory. Each client package is tested on the wire
// against a real server of its kind (internal/substrate, internal/ax,
// internal/k8s, internal/gcp); what these fakes test is the tick itself: what
// it reads, in which order, what it writes, and what it does only once the
// write stands. So they fake at the tick's own interfaces and record every
// call in one ordered list.
type world struct {
	t *testing.T

	mu    sync.Mutex
	calls []string

	// Substrate
	actors      []lease.ActorObs
	pending     bool
	actorsErr   error
	templateErr error

	// Kubernetes: "<ns>/<deployment>" -> replicas, and pods behind each
	replicas map[string]int
	pods     map[string]int
	scaleErr error
	setErr   error
	deleted  []string
	podsGone map[string]bool // "<ns>/<pod>/<uid>" already gone
	replaced map[string]bool // "<ns>/<pod>/<uid>" replaced under the same name
	// the images the pods in each namespace run, and a failing list
	podImages    map[string][]string
	podImagesErr map[string]error

	// AX
	suspended  []string
	noTask     map[string]bool
	suspendErr error
	axTasks    []ax.Task
	axDeleted  []string
	tasksErr   error

	// The reaper's configuration: the repositories retention manages, the
	// namespaces whose pods' images it protects, and the images it protects
	// that run outside the cluster.
	repos         []string
	podNamespaces []string
	protect       []string

	// Artifact Registry: repo -> packages, package -> tag id -> digest
	packages map[string][]string
	tags     map[string]map[string]string
	tagsErr  error
	tagged   []string // "<package> <id>"
	untagged []string

	// GCS: the ops bucket, with generations
	objects map[string]storedObject
	gen     int64
	getErr  map[string]error
	putErr  map[string]error
	puts    []string
}

type storedObject struct {
	body       []byte
	generation int64
}

const (
	router     = routerNamespace + "/" + routerDeployment
	controller = controllerNamespace + "/" + controllerDeployment
)

func newWorld(t *testing.T) *world {
	t.Helper()
	return &world{
		t:        t,
		replicas: map[string]int{router: 1, controller: 1},
		pods:     map[string]int{router: 1, controller: 1},
		podsGone: map[string]bool{},
		replaced: map[string]bool{},
		noTask:   map[string]bool{},
		repos:    []string{testRepo},

		podImages:    map[string][]string{},
		podImagesErr: map[string]error{},
		packages:     map[string][]string{},
		tags:         map[string]map[string]string{},
		objects:      map[string]storedObject{},
		getErr:       map[string]error{},
		putErr:       map[string]error{},
	}
}

func (w *world) call(format string, args ...any) {
	w.calls = append(w.calls, fmt.Sprintf(format, args...))
}

// reaper is a reaper wired to this world, logging into out.
func (w *world) reaper(out *logBuffer) *reaper {
	return &reaper{
		substrate: w, ax: w, k8s: w, gcs: w, ar: w,
		bucket: "zz-ops", repos: w.repos, podNamespaces: w.podNamespaces, protect: w.protect,
		log: l1Log{w: out},
	}
}

func (w *world) put(object string, v any) {
	w.t.Helper()
	body, err := json.Marshal(v)
	if err != nil {
		w.t.Fatal(err)
	}
	w.gen++
	w.objects[object] = storedObject{body: body, generation: w.gen}
}

func (w *world) drain() lease.Drain {
	w.t.Helper()
	var d lease.Drain
	o, ok := w.objects[ops.DrainObject]
	if !ok {
		return d
	}
	if err := json.Unmarshal(o.body, &d); err != nil {
		w.t.Fatal(err)
	}
	return d
}

// --- actorSource ---

func (w *world) Actors(context.Context) ([]lease.ActorObs, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.call("substrate.Actors")
	return slices.Clone(w.actors), w.actorsErr
}

func (w *world) TemplatesPending(context.Context) (bool, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.call("substrate.TemplatesPending")
	return w.pending, w.templateErr
}

// --- axAPI ---

func (w *world) Tasks(context.Context) ([]ax.Task, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.call("ax.Tasks")
	return slices.Clone(w.axTasks), w.tasksErr
}

func (w *world) Delete(_ context.Context, task string) error {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.call("ax.Delete %s", task)
	w.axDeleted = append(w.axDeleted, task)
	return nil
}

// --- tagStore ---

func (w *world) ListPackages(_ context.Context, repo string) ([]string, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.call("ar.ListPackages %s", repo)
	return slices.Clone(w.packages[repo]), w.tagsErr
}

func (w *world) ListTags(_ context.Context, pkg string) ([]gcp.ARTag, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.call("ar.ListTags %s", pkg)
	var out []gcp.ARTag
	for id, digest := range w.tags[pkg] {
		out = append(out, gcp.ARTag{ID: id, Digest: digest})
	}
	slices.SortFunc(out, func(a, b gcp.ARTag) int { return strings.Compare(a.ID, b.ID) })
	return out, w.tagsErr
}

func (w *world) CreateTag(_ context.Context, pkg, id, digest string) error {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.call("ar.CreateTag %s %s", pkg, id)
	if w.tags[pkg] == nil {
		w.tags[pkg] = map[string]string{}
	}
	w.tags[pkg][id] = digest
	w.tagged = append(w.tagged, pkg+" "+id)
	return nil
}

func (w *world) DeleteTag(_ context.Context, pkg, id string) error {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.call("ar.DeleteTag %s %s", pkg, id)
	delete(w.tags[pkg], id)
	w.untagged = append(w.untagged, pkg+" "+id)
	return nil
}

// --- taskSuspender ---

func (w *world) Suspend(_ context.Context, task string) error {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.call("ax.Suspend %s", task)
	if w.suspendErr != nil {
		return w.suspendErr
	}
	if w.noTask[task] {
		return fmt.Errorf("suspending %s: %w", task, ax.ErrNoTask)
	}
	w.suspended = append(w.suspended, task)
	return nil
}

// --- clusterAPI ---

func (w *world) Scale(_ context.Context, ns, deployment string) (int, string, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.call("k8s.Scale %s/%s", ns, deployment)
	if w.scaleErr != nil {
		return 0, "", w.scaleErr
	}
	return w.replicas[ns+"/"+deployment], "app=" + deployment, nil
}

func (w *world) SetScale(_ context.Context, ns, deployment string, n int) error {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.call("k8s.SetScale %s/%s %d", ns, deployment, n)
	if w.setErr != nil {
		return w.setErr
	}
	w.replicas[ns+"/"+deployment] = n
	return nil
}

func (w *world) CountPods(_ context.Context, ns, selector string) (int, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.call("k8s.CountPods %s %s", ns, selector)
	return w.pods[ns+"/"+strings.TrimPrefix(selector, "app=")], nil
}

func (w *world) PodImages(_ context.Context, ns string) ([]string, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.call("k8s.PodImages %s", ns)
	if err := w.podImagesErr[ns]; err != nil {
		return nil, err
	}
	return w.podImages[ns], nil
}

func (w *world) DeletePod(_ context.Context, ns, name, uid string) error {
	w.mu.Lock()
	defer w.mu.Unlock()
	key := ns + "/" + name + "/" + uid
	w.call("k8s.DeletePod %s", key)
	if w.replaced[key] {
		return fmt.Errorf("deleting pod %s: %w", key, k8s.ErrPodReplaced)
	}
	if !w.podsGone[key] {
		w.deleted = append(w.deleted, key)
		w.podsGone[key] = true
	}
	return nil
}

// --- objectStore ---

func (w *world) GetObject(_ context.Context, _ string, object string) ([]byte, int64, error) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.call("gcs.Get %s", object)
	if err := w.getErr[object]; err != nil {
		return nil, 0, err
	}
	o, ok := w.objects[object]
	if !ok {
		return nil, 0, fmt.Errorf("%s: %w", object, gcp.ErrNotFound)
	}
	return slices.Clone(o.body), o.generation, nil
}

func (w *world) PutObject(_ context.Context, _ string, object string, data []byte, ifGeneration int64) error {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.call("gcs.Put %s", object)
	if err := w.putErr[object]; err != nil {
		return err
	}
	if o, ok := w.objects[object]; ifGeneration >= 0 && ((ok && o.generation != ifGeneration) || (!ok && ifGeneration != 0)) {
		return fmt.Errorf("%s: %w", object, gcp.ErrPreconditionFailed)
	}
	w.gen++
	w.objects[object] = storedObject{body: slices.Clone(data), generation: w.gen}
	w.puts = append(w.puts, object)
	return nil
}

// --- the log -------------------------------------------------------------------

// logBuffer collects the tick's log lines.
type logBuffer struct {
	mu    sync.Mutex
	lines []map[string]any
	raw   []string
}

func (b *logBuffer) Write(p []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	for _, line := range splitLines(p) {
		b.raw = append(b.raw, line)
		var m map[string]any
		if err := json.Unmarshal([]byte(line), &m); err != nil {
			return 0, fmt.Errorf("log line is not JSON: %q", line)
		}
		b.lines = append(b.lines, m)
	}
	return len(p), nil
}

func splitLines(p []byte) []string {
	var out []string
	start := 0
	for i, c := range p {
		if c == '\n' {
			if i > start {
				out = append(out, string(p[start:i]))
			}
			start = i + 1
		}
	}
	if start < len(p) {
		out = append(out, string(p[start:]))
	}
	return out
}

// events is every line's exe_l1.event with its severity, "event/SEVERITY".
func (b *logBuffer) events() []string {
	b.mu.Lock()
	defer b.mu.Unlock()
	var out []string
	for _, l := range b.lines {
		payload, _ := l["exe_l1"].(map[string]any)
		out = append(out, fmt.Sprintf("%v/%v", payload["event"], l["severity"]))
	}
	return out
}

// decision is the one decision line's payload.
func (b *logBuffer) decision(t *testing.T) map[string]any {
	t.Helper()
	b.mu.Lock()
	defer b.mu.Unlock()
	var found []map[string]any
	for _, l := range b.lines {
		if payload, _ := l["exe_l1"].(map[string]any); payload["event"] == "decision" {
			found = append(found, payload)
		}
	}
	if len(found) != 1 {
		t.Fatalf("want one decision line, got %d: %v", len(found), b.raw)
	}
	return found[0]
}

var errBoom = errors.New("boom")
