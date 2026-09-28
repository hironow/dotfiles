package gcp

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"slices"
	"strings"
	"sync"
	"testing"
)

// The Artifact Registry half: the tags L1 keeps on the images live tasks and
// the cluster use (plan D10). Same approach as the GCS tests above: an
// httptest server, so the real URLs, escaping, pagination and status handling
// run.

const (
	testRepo = "projects/zz-p/locations/asia-northeast1/repositories/exe-task"
	testPkg  = testRepo + "/packages/task"
	// A package with a slash in its name, as ko's are: the API escapes it.
	testNestedPkg = "projects/zz-p/locations/asia-northeast1/repositories/exe-platform/packages/substrate%2Fateapi"
)

// fakeAR is Artifact Registry's REST API for packages and tags.
type fakeAR struct {
	mu       sync.Mutex
	packages map[string][]string          // repo -> package names
	tags     map[string]map[string]string // package -> tag id -> version name
	pageSize int
	requests []string
}

func (f *fakeAR) serve(w http.ResponseWriter, r *http.Request) {
	f.mu.Lock()
	defer f.mu.Unlock()
	// The resource name is everything after /v1/, with any %2F kept escaped.
	path := strings.TrimPrefix(r.URL.EscapedPath(), "/v1/")
	f.requests = append(f.requests, r.Method+" "+path)
	switch {
	case r.Method == http.MethodGet && strings.HasSuffix(path, "/packages"):
		f.page(w, r, "packages", f.named(f.packages[strings.TrimSuffix(path, "/packages")]))
	case r.Method == http.MethodGet && strings.HasSuffix(path, "/tags"):
		pkg := strings.TrimSuffix(path, "/tags")
		var items []map[string]string
		ids := make([]string, 0, len(f.tags[pkg]))
		for id := range f.tags[pkg] {
			ids = append(ids, id)
		}
		slices.Sort(ids)
		for _, id := range ids {
			items = append(items, map[string]string{"name": pkg + "/tags/" + id, "version": f.tags[pkg][id]})
		}
		f.page(w, r, "tags", items)
	case r.Method == http.MethodPost && strings.HasSuffix(path, "/tags"):
		pkg := strings.TrimSuffix(path, "/tags")
		id := r.URL.Query().Get("tagId")
		var body struct {
			Version string `json:"version"`
		}
		raw, _ := io.ReadAll(r.Body)
		if err := json.Unmarshal(raw, &body); err != nil || id == "" || body.Version == "" {
			http.Error(w, "bad create "+string(raw), http.StatusBadRequest)
			return
		}
		if _, exists := f.tags[pkg][id]; exists {
			http.Error(w, `{"error":{"status":"ALREADY_EXISTS"}}`, http.StatusConflict)
			return
		}
		if f.tags[pkg] == nil {
			f.tags[pkg] = map[string]string{}
		}
		f.tags[pkg][id] = body.Version
		_ = json.NewEncoder(w).Encode(map[string]string{"name": pkg + "/tags/" + id, "version": body.Version})
	case r.Method == http.MethodDelete && strings.Contains(path, "/tags/"):
		pkg, id, _ := strings.Cut(path, "/tags/")
		if _, exists := f.tags[pkg][id]; !exists {
			http.Error(w, `{"error":{"status":"NOT_FOUND"}}`, http.StatusNotFound)
			return
		}
		delete(f.tags[pkg], id)
		_, _ = w.Write([]byte("{}"))
	default:
		http.Error(w, "unexpected "+r.Method+" "+path, http.StatusNotFound)
	}
}

func (f *fakeAR) named(names []string) []map[string]string {
	var out []map[string]string
	for _, n := range names {
		out = append(out, map[string]string{"name": n})
	}
	return out
}

// page serves items in pages of f.pageSize, the token being the next index.
func (f *fakeAR) page(w http.ResponseWriter, r *http.Request, field string, items []map[string]string) {
	start := 0
	if tok := r.URL.Query().Get("pageToken"); tok != "" {
		start = len(tok)
	}
	end := len(items)
	if f.pageSize > 0 && start+f.pageSize < end {
		end = start + f.pageSize
	}
	resp := map[string]any{field: items[start:end]}
	if end < len(items) {
		resp["nextPageToken"] = strings.Repeat(".", end)
	}
	_ = json.NewEncoder(w).Encode(resp)
}

func arClient(t *testing.T, f *fakeAR) *Client {
	t.Helper()
	client, srv := testClient(t, f.serve)
	// The override replaces the whole base, version segment included.
	client.ArtifactRegistryBase = srv.URL + "/v1"
	return client
}

func TestListPackagesFollowsEveryPage(t *testing.T) {
	f := &fakeAR{pageSize: 1, packages: map[string][]string{
		testRepo: {testRepo + "/packages/task", testRepo + "/packages/other"},
	}}
	got, err := arClient(t, f).ListPackages(context.Background(), testRepo)
	if err != nil {
		t.Fatal(err)
	}
	if want := []string{testRepo + "/packages/task", testRepo + "/packages/other"}; !slices.Equal(got, want) {
		t.Errorf("packages %v, want %v", got, want)
	}
}

func TestListTagsReadsEveryPageAndKeepsTheEscapedPackageName(t *testing.T) {
	f := &fakeAR{pageSize: 1, tags: map[string]map[string]string{
		testNestedPkg: {
			"inuse-aaaaaaaaaaaa": testNestedPkg + "/versions/sha256:aaaa",
			"v1":                 testNestedPkg + "/versions/sha256:bbbb",
		},
	}}
	got, err := arClient(t, f).ListTags(context.Background(), testNestedPkg)
	if err != nil {
		t.Fatal(err)
	}
	want := []ARTag{
		{ID: "inuse-aaaaaaaaaaaa", Digest: "sha256:aaaa"},
		{ID: "v1", Digest: "sha256:bbbb"},
	}
	if !slices.Equal(got, want) {
		t.Errorf("tags %+v, want %+v", got, want)
	}
	for _, req := range f.requests {
		if strings.Contains(req, "substrate/ateapi") {
			t.Errorf("request %q unescaped the package name: its slash would be a path separator", req)
		}
	}
}

func TestCreateTagPointsTheTagAtTheDigestAndAnExistingOneIsFine(t *testing.T) {
	f := &fakeAR{tags: map[string]map[string]string{}}
	c := arClient(t, f)

	if err := c.CreateTag(context.Background(), testPkg, "inuse-aaaaaaaaaaaa", "sha256:aaaa"); err != nil {
		t.Fatal(err)
	}
	if got := f.tags[testPkg]["inuse-aaaaaaaaaaaa"]; got != testPkg+"/versions/sha256:aaaa" {
		t.Errorf("tag points at %q", got)
	}
	// A tag that is already there is the goal holding, not an error.
	if err := c.CreateTag(context.Background(), testPkg, "inuse-aaaaaaaaaaaa", "sha256:aaaa"); err != nil {
		t.Errorf("creating an existing tag: %v", err)
	}
}

func TestDeleteTagOfATagAlreadyGoneIsFine(t *testing.T) {
	f := &fakeAR{tags: map[string]map[string]string{testPkg: {"inuse-aaaaaaaaaaaa": testPkg + "/versions/sha256:aaaa"}}}
	c := arClient(t, f)

	if err := c.DeleteTag(context.Background(), testPkg, "inuse-aaaaaaaaaaaa"); err != nil {
		t.Fatal(err)
	}
	if _, still := f.tags[testPkg]["inuse-aaaaaaaaaaaa"]; still {
		t.Error("the tag is still there")
	}
	if err := c.DeleteTag(context.Background(), testPkg, "inuse-aaaaaaaaaaaa"); err != nil {
		t.Errorf("deleting a tag that is gone: %v", err)
	}
}

func TestAnyOtherARFailureIsAnError(t *testing.T) {
	client, _ := testClient(t, func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "denied", http.StatusForbidden)
	})
	client.ArtifactRegistryBase = client.StorageBase
	ctx := context.Background()
	if _, err := client.ListTags(ctx, testPkg); err == nil {
		t.Error("a refused list reported success")
	}
	if err := client.CreateTag(ctx, testPkg, "inuse-x", "sha256:x"); err == nil {
		t.Error("a refused create reported success")
	}
	if err := client.DeleteTag(ctx, testPkg, "inuse-x"); err == nil {
		t.Error("a refused delete reported success")
	}
}

func TestParseImageRef(t *testing.T) {
	tests := []struct {
		ref, repo, pkg, digest string
		ok                     bool
	}{
		{
			"asia-northeast1-docker.pkg.dev/zz-p/exe-task/task:42ec@sha256:4f2b",
			"projects/zz-p/locations/asia-northeast1/repositories/exe-task",
			"projects/zz-p/locations/asia-northeast1/repositories/exe-task/packages/task",
			"sha256:4f2b", true,
		},
		{
			"asia-northeast1-docker.pkg.dev/zz-p/exe-platform/substrate/ateapi@sha256:abcd",
			"projects/zz-p/locations/asia-northeast1/repositories/exe-platform",
			"projects/zz-p/locations/asia-northeast1/repositories/exe-platform/packages/substrate%2Fateapi",
			"sha256:abcd", true,
		},
		// not pinned by digest: nothing a tag could protect
		{"asia-northeast1-docker.pkg.dev/zz-p/exe-task/task:latest", "", "", "", false},
		// not Artifact Registry
		{"redis:7-alpine@sha256:858f", "", "", "", false},
		{"ghcr.io/x/y@sha256:1", "", "", "", false},
		{"", "", "", "", false},
	}
	for _, tc := range tests {
		repo, pkg, digest, ok := ParseImageRef(tc.ref)
		if repo != tc.repo || pkg != tc.pkg || digest != tc.digest || ok != tc.ok {
			t.Errorf("ParseImageRef(%q) = %q %q %q %t", tc.ref, repo, pkg, digest, ok)
		}
	}
}
