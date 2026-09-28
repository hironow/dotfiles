package k8s

import (
	"context"
	"encoding/json"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"sync"
	"testing"
)

// fakeAPI is the slice of the Kubernetes API one L1 tick touches: the scale
// subresource of two Deployments, a pod list, and a pod delete. An httptest
// TLS server rather than a mocked interface, so URLs, headers, bodies and
// status handling run for real. Anything else is a 404 and fails loudly.
type fakeAPI struct {
	t   *testing.T
	srv *httptest.Server

	mu       sync.Mutex
	replicas map[string]int // "<ns>/<deployment>"
	selector map[string]string
	pods     map[string][]fakePod // "<ns>" -> pods
	pageSize int                  // pods per list page (0: all at once)
	status   int                  // non-zero: every request answers with it
	tokens   []string
	patches  []string // "<ns>/<deployment>=<body>"
	deletes  []string // "<ns>/<pod>/<uid>"
}

type fakePod struct {
	name, uid, labels, phase string
	terminating              bool
	// images and initImages are the spec's; imageIDs and initImageIDs the
	// status's, one per started container.
	images, initImages, imageIDs, initImageIDs []string
}

func newFakeAPI(t *testing.T) *fakeAPI {
	t.Helper()
	f := &fakeAPI{t: t, replicas: map[string]int{}, selector: map[string]string{}, pods: map[string][]fakePod{}}
	f.srv = httptest.NewTLSServer(http.HandlerFunc(f.serve))
	t.Cleanup(f.srv.Close)
	return f
}

// client is a Client for f, with f's certificate as the cluster CA and a token
// file holding "token-one".
func (f *fakeAPI) client() (*Client, string) {
	f.t.Helper()
	dir := f.t.TempDir()
	ca := filepath.Join(dir, "ca.crt")
	token := filepath.Join(dir, "token")
	if err := os.WriteFile(ca, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: f.srv.Certificate().Raw}), 0o600); err != nil {
		f.t.Fatal(err)
	}
	if err := os.WriteFile(token, []byte("token-one\n"), 0o600); err != nil {
		f.t.Fatal(err)
	}
	c, err := New(Config{Host: f.srv.URL, CAFile: ca, TokenFile: token})
	if err != nil {
		f.t.Fatal(err)
	}
	return c, token
}

func (f *fakeAPI) serve(w http.ResponseWriter, r *http.Request) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.tokens = append(f.tokens, r.Header.Get("Authorization"))
	if f.status != 0 {
		http.Error(w, `{"kind":"Status","message":"refused"}`, f.status)
		return
	}
	parts := strings.Split(strings.Trim(r.URL.Path, "/"), "/")
	switch {
	// /apis/apps/v1/namespaces/{ns}/deployments/{name}/scale
	case len(parts) == 8 && parts[0] == "apis" && parts[1] == "apps" && parts[5] == "deployments" && parts[7] == "scale":
		key := parts[4] + "/" + parts[6]
		n, ok := f.replicas[key]
		if !ok {
			http.NotFound(w, r)
			return
		}
		switch r.Method {
		case http.MethodGet:
		case http.MethodPatch:
			body, _ := io.ReadAll(r.Body)
			if ct := r.Header.Get("Content-Type"); ct != "application/merge-patch+json" {
				http.Error(w, "content type "+ct, http.StatusUnsupportedMediaType)
				return
			}
			var patch struct {
				Spec struct {
					Replicas *int `json:"replicas"`
				} `json:"spec"`
			}
			if err := json.Unmarshal(body, &patch); err != nil || patch.Spec.Replicas == nil {
				http.Error(w, "bad patch "+string(body), http.StatusBadRequest)
				return
			}
			n = *patch.Spec.Replicas
			f.replicas[key] = n
			f.patches = append(f.patches, key+"="+string(body))
		default:
			http.Error(w, "method", http.StatusMethodNotAllowed)
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"kind": "Scale", "apiVersion": "autoscaling/v1",
			"spec":   map[string]any{"replicas": n},
			"status": map[string]any{"replicas": n, "selector": f.selector[key]},
		})
	// /api/v1/namespaces/{ns}/pods
	case len(parts) == 5 && parts[0] == "api" && parts[4] == "pods" && r.Method == http.MethodGet:
		f.listPods(w, r, parts[3])
	// /api/v1/namespaces/{ns}/pods/{name}
	case len(parts) == 6 && parts[0] == "api" && parts[4] == "pods" && r.Method == http.MethodDelete:
		f.deletePod(w, r, parts[3], parts[5])
	default:
		http.NotFound(w, r)
	}
}

func (f *fakeAPI) listPods(w http.ResponseWriter, r *http.Request, ns string) {
	sel := r.URL.Query().Get("labelSelector")
	var matched []fakePod
	for _, p := range f.pods[ns] {
		if sel == "" || p.labels == sel {
			matched = append(matched, p)
		}
	}
	start := 0
	if c := r.URL.Query().Get("continue"); c != "" {
		start = len(c) // the continue token is start's worth of dots
	}
	end := len(matched)
	if f.pageSize > 0 && start+f.pageSize < end {
		end = start + f.pageSize
	}
	containers := func(images []string) []map[string]any {
		out := []map[string]any{}
		for i, img := range images {
			out = append(out, map[string]any{"name": fmt.Sprintf("c%d", i), "image": img})
		}
		return out
	}
	statuses := func(ids []string) []map[string]any {
		out := []map[string]any{}
		for i, id := range ids {
			out = append(out, map[string]any{"name": fmt.Sprintf("c%d", i), "imageID": id})
		}
		return out
	}
	items := []map[string]any{}
	for _, p := range matched[start:end] {
		meta := map[string]any{"name": p.name, "uid": p.uid}
		if p.terminating {
			meta["deletionTimestamp"] = "2026-09-28T00:00:00Z"
		}
		items = append(items, map[string]any{
			"metadata": meta,
			"spec":     map[string]any{"containers": containers(p.images), "initContainers": containers(p.initImages)},
			"status": map[string]any{
				"phase":                 p.phase,
				"containerStatuses":     statuses(p.imageIDs),
				"initContainerStatuses": statuses(p.initImageIDs),
			},
		})
	}
	cont := ""
	if end < len(matched) {
		cont = strings.Repeat(".", end)
	}
	_ = json.NewEncoder(w).Encode(map[string]any{"kind": "PodList", "items": items, "metadata": map[string]any{"continue": cont}})
}

func (f *fakeAPI) deletePod(w http.ResponseWriter, r *http.Request, ns, name string) {
	var opts struct {
		Preconditions struct {
			UID string `json:"uid"`
		} `json:"preconditions"`
	}
	body, _ := io.ReadAll(r.Body)
	if err := json.Unmarshal(body, &opts); err != nil {
		http.Error(w, "bad delete options "+string(body), http.StatusBadRequest)
		return
	}
	pods := f.pods[ns]
	for i, p := range pods {
		if p.name != name {
			continue
		}
		if opts.Preconditions.UID != p.uid {
			http.Error(w, `{"kind":"Status","reason":"Conflict"}`, http.StatusConflict)
			return
		}
		f.pods[ns] = slices.Delete(pods, i, i+1)
		f.deletes = append(f.deletes, ns+"/"+name+"/"+p.uid)
		_ = json.NewEncoder(w).Encode(map[string]any{"kind": "Pod"})
		return
	}
	http.NotFound(w, r)
}

func TestScaleReadsTheCountAndTheSelector(t *testing.T) {
	f := newFakeAPI(t)
	f.replicas["ate-system/atenet-router"] = 1
	f.selector["ate-system/atenet-router"] = "app=atenet-router"
	c, _ := f.client()

	n, sel, err := c.Scale(context.Background(), "ate-system", "atenet-router")
	if err != nil {
		t.Fatal(err)
	}
	if n != 1 || sel != "app=atenet-router" {
		t.Errorf("scale %d / %q, want 1 / app=atenet-router", n, sel)
	}
}

func TestSetScalePatchesTheReplicaCountAndNothingElse(t *testing.T) {
	f := newFakeAPI(t)
	f.replicas["ax-system/ax-controller"] = 1
	c, _ := f.client()

	if err := c.SetScale(context.Background(), "ax-system", "ax-controller", 0); err != nil {
		t.Fatal(err)
	}
	if want := []string{`ax-system/ax-controller={"spec":{"replicas":0}}`}; !slices.Equal(f.patches, want) {
		t.Errorf("patches %q, want %q", f.patches, want)
	}
	if f.replicas["ax-system/ax-controller"] != 0 {
		t.Errorf("replicas %d after the patch, want 0", f.replicas["ax-system/ax-controller"])
	}
}

func TestCountPodsFollowsEveryPageAndCountsWhatCanStillRun(t *testing.T) {
	// A terminating pod still serves until it is gone, so it counts (plan D2
	// step 6). A pod that finished -- evicted, OOM-killed, completed -- runs
	// nothing and would otherwise hold a drain until the pod GC.
	f := newFakeAPI(t)
	f.pageSize = 2
	f.pods["ax-system"] = []fakePod{
		{name: "c1", uid: "1", labels: "app=ax-controller", phase: "Running"},
		{name: "c2", uid: "2", labels: "app=ax-controller", phase: "Running", terminating: true},
		{name: "c3", uid: "3", labels: "app=ax-controller", phase: "Failed"},
		{name: "c4", uid: "4", labels: "app=ax-controller", phase: "Pending"},
		{name: "c5", uid: "5", labels: "app=ax-controller", phase: "Succeeded"},
		{name: "s1", uid: "6", labels: "app=ax-server", phase: "Running"},
	}
	c, _ := f.client()

	n, err := c.CountPods(context.Background(), "ax-system", "app=ax-controller")
	if err != nil {
		t.Fatal(err)
	}
	if n != 3 {
		t.Errorf("counted %d pods, want 3 (running, terminating, pending)", n)
	}
}

func TestPodImagesListsWhatEveryPodRunsPinnedByDigest(t *testing.T) {
	// A started container's status holds the digest its node pulled, even
	// when the spec names a tag; a pod not started yet has only its spec, and
	// that counts when it is pinned by digest. Init containers run images
	// too. An image the node built or loaded itself has no repository, so
	// nothing to protect.
	const (
		reg = "asia-northeast1-docker.pkg.dev/zz-p/exe-platform/"
		dA  = "sha256:aaaaaaaaaaaa1111111111111111111111111111111111111111111111111111"
		dB  = "sha256:bbbbbbbbbbbb2222222222222222222222222222222222222222222222222222"
		dC  = "sha256:cccccccccccc3333333333333333333333333333333333333333333333333333"
	)
	f := newFakeAPI(t)
	f.pageSize = 1
	f.pods["ate-system"] = []fakePod{
		{
			name: "api-1", uid: "1", phase: "Running",
			images: []string{reg + "ate-api:v1"}, imageIDs: []string{reg + "ate-api@" + dA},
			initImages: []string{reg + "init:v1"}, initImageIDs: []string{"docker-pullable://" + reg + "init@" + dB},
		},
		{name: "api-2", uid: "2", phase: "Running", images: []string{reg + "ate-api:v1"}, imageIDs: []string{reg + "ate-api@" + dA}},
		{name: "starting", uid: "3", phase: "Pending", images: []string{reg + "atelet@" + dC, reg + "sidecar:latest"}},
		{name: "local", uid: "4", phase: "Running", images: []string{"pause"}, imageIDs: []string{dA}},
	}
	c, _ := f.client()

	got, err := c.PodImages(context.Background(), "ate-system")
	if err != nil {
		t.Fatal(err)
	}
	want := []string{reg + "ate-api@" + dA, reg + "atelet@" + dC, reg + "init@" + dB}
	if !slices.Equal(got, want) {
		t.Errorf("images %q, want %q", got, want)
	}
}

func TestCountPodsRefusesAnEmptySelector(t *testing.T) {
	// An empty selector lists every pod in the namespace: a Deployment whose
	// scale reports no selector would make L1 wait on pods that are not its.
	c, _ := newFakeAPI(t).client()
	if _, err := c.CountPods(context.Background(), "ax-system", ""); err == nil {
		t.Error("counted pods with an empty selector")
	}
}

func TestDeletePodDeletesOnlyThePodItNamesByUID(t *testing.T) {
	f := newFakeAPI(t)
	f.pods["exe"] = []fakePod{{name: "w-a", uid: "new-uid", phase: "Running"}}
	c, _ := f.client()

	// a pod that was replaced under the same name is not deleted
	if err := c.DeletePod(context.Background(), "exe", "w-a", "old-uid"); !errors.Is(err, ErrPodReplaced) {
		t.Errorf("err = %v, want ErrPodReplaced", err)
	}
	if len(f.deletes) != 0 {
		t.Fatalf("deleted %v", f.deletes)
	}
	// the pod the store named is
	if err := c.DeletePod(context.Background(), "exe", "w-a", "new-uid"); err != nil {
		t.Fatal(err)
	}
	if want := []string{"exe/w-a/new-uid"}; !slices.Equal(f.deletes, want) {
		t.Errorf("deletes %v, want %v", f.deletes, want)
	}
	// and one already gone is not an error: the delete's goal holds
	if err := c.DeletePod(context.Background(), "exe", "w-a", "new-uid"); err != nil {
		t.Errorf("deleting a pod that is gone: %v", err)
	}
}

func TestEveryRequestCarriesTheCurrentToken(t *testing.T) {
	f := newFakeAPI(t)
	f.replicas["ate-system/atenet-router"] = 1
	c, token := f.client()

	if _, _, err := c.Scale(context.Background(), "ate-system", "atenet-router"); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(token, []byte("token-two"), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, _, err := c.Scale(context.Background(), "ate-system", "atenet-router"); err != nil {
		t.Fatal(err)
	}
	if want := []string{"Bearer token-one", "Bearer token-two"}; !slices.Equal(f.tokens, want) {
		t.Errorf("tokens %q, want %q", f.tokens, want)
	}
}

func TestARefusalIsAnErrorThatSaysSo(t *testing.T) {
	f := newFakeAPI(t)
	f.status = http.StatusForbidden
	c, _ := f.client()

	_, _, err := c.Scale(context.Background(), "ate-system", "atenet-router")
	if err == nil || !strings.Contains(err.Error(), "403") {
		t.Errorf("err = %v, want one naming the 403", err)
	}
	if err := c.SetScale(context.Background(), "ate-system", "atenet-router", 0); err == nil {
		t.Error("a refused patch reported success")
	}
	if _, err := c.CountPods(context.Background(), "ate-system", "app=x"); err == nil {
		t.Error("a refused list reported success")
	}
	if _, err := c.PodImages(context.Background(), "ate-system"); err == nil {
		t.Error("a refused image list reported success")
	}
	if err := c.DeletePod(context.Background(), "exe", "w-a", "u"); err == nil || errors.Is(err, ErrPodReplaced) {
		t.Errorf("a refused delete: %v", err)
	}
}
