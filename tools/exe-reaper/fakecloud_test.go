package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/gcp"
)

// fakeCloud stands in for every Google endpoint one L2 tick touches: the GCS
// media download and upload (with real generation preconditions), the GKE node
// pool GET, its managed instance group GET, and nodePools.setSize.
//
// An httptest server rather than a mocked interface, for the reason
// internal/gcp gives: the tick runs its real HTTP client against it, so URLs,
// query parameters and status handling are exercised rather than re-asserted.
// It models only what the tick depends on; anything else is a 404 and fails the
// test loudly.
type fakeCloud struct {
	t   *testing.T
	srv *httptest.Server

	mu         sync.Mutex
	objects    map[string]fakeObject
	generation int64 // the last generation handed out; GCS's are positive
	getStatus  map[string]int
	gets       map[string]int
	// beforeGet runs under the lock before the nth GET of an object is
	// served (n counts from 1), so a test can change the world between two
	// reads of one tick.
	beforeGet    func(f *fakeCloud, object string, n int)
	sizeStatus   int
	targetSize   int
	setSizeCalls []int
}

type fakeObject struct {
	body       []byte
	generation int64
}

const (
	fakeBucket = "zz-ops"
	fakePool   = "zz-pool"
)

func newFakeCloud(t *testing.T) *fakeCloud {
	t.Helper()
	f := &fakeCloud{
		t:         t,
		objects:   map[string]fakeObject{},
		getStatus: map[string]int{},
		gets:      map[string]int{},
	}
	f.srv = httptest.NewServer(http.HandlerFunc(f.serve))
	t.Cleanup(f.srv.Close)
	return f
}

// enforcer returns an enforcer wired to this fake, reporting into out.
func (f *fakeCloud) enforcer(out io.Writer) enforcer {
	return enforcer{
		client: &gcp.Client{
			HTTP:          f.srv.Client(),
			Token:         func(context.Context) (string, error) { return "test-token", nil },
			StorageBase:   f.srv.URL,
			ContainerBase: f.srv.URL,
		},
		cfg: config{
			bucket:     fakeBucket,
			setSizeURI: f.srv.URL + "/v1/projects/zz-project/locations/zz-zone/clusters/zz-cluster/nodePools/" + fakePool + ":setSize",
			project:    "zz-project",
			zone:       "zz-zone",
			cluster:    "zz-cluster",
			nodePool:   fakePool,
		},
		out:    out,
		errOut: out,
	}
}

// put stores an object as a new generation, as a write by its owner would.
func (f *fakeCloud) put(object string, value any) {
	f.t.Helper()
	body, err := json.Marshal(value)
	if err != nil {
		f.t.Fatalf("marshalling %s: %v", object, err)
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	f.store(object, body)
}

func (f *fakeCloud) store(object string, body []byte) {
	f.generation++
	f.objects[object] = fakeObject{body: body, generation: f.generation}
}

// object returns what is stored, failing the test if nothing is.
func (f *fakeCloud) object(object string) fakeObject {
	f.t.Helper()
	f.mu.Lock()
	defer f.mu.Unlock()
	o, ok := f.objects[object]
	if !ok {
		f.t.Fatalf("%s was never written", object)
	}
	return o
}

func (f *fakeCloud) setSizes() []int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]int(nil), f.setSizeCalls...)
}

func (f *fakeCloud) serve(w http.ResponseWriter, r *http.Request) {
	f.mu.Lock()
	defer f.mu.Unlock()

	storagePrefix := "/storage/v1/b/" + fakeBucket + "/o/"
	poolPath := "/v1/projects/zz-project/locations/zz-zone/clusters/zz-cluster/nodePools/" + fakePool
	switch {
	case r.Method == http.MethodGet && strings.HasPrefix(r.URL.Path, storagePrefix):
		f.serveGet(w, strings.TrimPrefix(r.URL.Path, storagePrefix))
	case r.Method == http.MethodPost && r.URL.Path == "/upload/storage/v1/b/"+fakeBucket+"/o":
		f.servePut(w, r)
	case r.Method == http.MethodGet && r.URL.Path == poolPath:
		if f.sizeStatus != 0 {
			w.WriteHeader(f.sizeStatus)
			return
		}
		_, _ = fmt.Fprintf(w, `{"instanceGroupUrls":[%q]}`, f.srv.URL+"/compute/v1/zz-igm")
	case r.Method == http.MethodGet && r.URL.Path == "/compute/v1/zz-igm":
		_, _ = fmt.Fprintf(w, `{"targetSize":%d}`, f.targetSize)
	case r.Method == http.MethodPost && r.URL.Path == poolPath+":setSize":
		var req struct {
			NodeCount int `json:"nodeCount"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		f.setSizeCalls = append(f.setSizeCalls, req.NodeCount)
		f.targetSize = req.NodeCount
		_, _ = w.Write([]byte(`{"name":"operation-zz"}`))
	default:
		f.t.Errorf("fakeCloud: unexpected %s %s", r.Method, r.URL.Path)
		w.WriteHeader(http.StatusNotFound)
	}
}

func (f *fakeCloud) serveGet(w http.ResponseWriter, object string) {
	f.gets[object]++
	if f.beforeGet != nil {
		f.beforeGet(f, object, f.gets[object])
	}
	if status := f.getStatus[object]; status != 0 {
		w.WriteHeader(status)
		return
	}
	o, ok := f.objects[object]
	if !ok {
		w.WriteHeader(http.StatusNotFound)
		return
	}
	w.Header().Set("X-Goog-Generation", strconv.FormatInt(o.generation, 10))
	_, _ = w.Write(o.body)
}

// servePut honours ifGenerationMatch as GCS does: 0 means "only if absent",
// a positive number means "only if that is the live generation".
func (f *fakeCloud) servePut(w http.ResponseWriter, r *http.Request) {
	object := r.URL.Query().Get("name")
	if raw := r.URL.Query().Get("ifGenerationMatch"); raw != "" {
		want, err := strconv.ParseInt(raw, 10, 64)
		if err != nil {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		if f.objects[object].generation != want {
			w.WriteHeader(http.StatusPreconditionFailed)
			return
		}
	}
	body, err := io.ReadAll(r.Body)
	if err != nil {
		w.WriteHeader(http.StatusBadRequest)
		return
	}
	f.store(object, body)
	w.WriteHeader(http.StatusOK)
}

// storedRecord decodes enforce.json as the tick left it.
func (f *fakeCloud) storedRecord() enforceRecord {
	f.t.Helper()
	var rec enforceRecord
	if err := json.Unmarshal(f.object(enforceObject).body, &rec); err != nil {
		f.t.Fatalf("enforce.json is not a record: %v", err)
	}
	return rec
}

// tickAt runs one tick at now and fails the test on an error.
func (f *fakeCloud) tickAt(now time.Time, out io.Writer) {
	f.t.Helper()
	if err := f.enforcer(out).tick(f.t.Context(), now, false); err != nil {
		f.t.Fatalf("tick: %v", err)
	}
}
