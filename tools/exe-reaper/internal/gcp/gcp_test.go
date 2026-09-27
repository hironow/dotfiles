package gcp

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
)

// httptest, not a mocked interface: what is worth testing here is that the
// right URL, the right query parameters and the right status handling actually
// happen, and a hand-written fake of my own client would assert only that I
// wrote the same thing twice.
//
// The distinction these tests protect is load-bearing: "the object is absent"
// and "GCS did not answer" must not be the same error. Absent means the cluster
// is not authorised; unanswered means try again. Conflating them turns a
// transient network blip into a destroyed workspace — which is exactly why L2's
// rule needs three consecutive failures.

func testClient(t *testing.T, handler http.HandlerFunc) (*Client, *httptest.Server) {
	t.Helper()
	srv := httptest.NewServer(handler)
	t.Cleanup(srv.Close)
	return &Client{
		HTTP:          srv.Client(),
		Token:         func(context.Context) (string, error) { return "test-token", nil },
		StorageBase:   srv.URL,
		ContainerBase: srv.URL,
	}, srv
}

func TestGetObjectReturnsBodyAndGeneration(t *testing.T) {
	var gotPath, gotAuth, gotQuery string
	client, _ := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		gotPath, gotAuth, gotQuery = r.URL.Path, r.Header.Get("Authorization"), r.URL.RawQuery
		w.Header().Set("X-Goog-Generation", "1234567890")
		_, _ = w.Write([]byte(`{"deadline":"2026-09-27T12:00:00Z"}`))
	})

	data, generation, err := client.GetObject(context.Background(), "zz-bucket", "lease.json")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(string(data), "deadline") {
		t.Errorf("body not returned: %q", data)
	}
	if generation != 1234567890 {
		t.Errorf("generation: want 1234567890, got %d", generation)
	}
	if gotAuth != "Bearer test-token" {
		t.Errorf("authorization header: %q", gotAuth)
	}
	if want := "/storage/v1/b/zz-bucket/o/lease.json"; gotPath != want {
		t.Errorf("path: want %q, got %q", want, gotPath)
	}
	if !strings.Contains(gotQuery, "alt=media") {
		t.Errorf("query should request the media download: %q", gotQuery)
	}
}

func TestGetObjectDistinguishesAbsentFromBroken(t *testing.T) {
	tests := []struct {
		name   string
		status int
		wantIs error
	}{
		{"absent is ErrNotFound", http.StatusNotFound, ErrNotFound},
		{"server error is not ErrNotFound", http.StatusInternalServerError, nil},
		{"permission denied is not ErrNotFound", http.StatusForbidden, nil},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			client, _ := testClient(t, func(w http.ResponseWriter, _ *http.Request) {
				w.WriteHeader(tc.status)
			})
			_, _, err := client.GetObject(context.Background(), "zz-bucket", "lease.json")
			if err == nil {
				t.Fatal("want an error")
			}
			if tc.wantIs != nil && !errors.Is(err, tc.wantIs) {
				t.Errorf("want errors.Is(..., ErrNotFound); got %v", err)
			}
			if tc.wantIs == nil && errors.Is(err, ErrNotFound) {
				t.Errorf("a %d must not read as ErrNotFound: %v", tc.status, err)
			}
		})
	}
}

func TestPutObjectSendsTheGenerationPrecondition(t *testing.T) {
	tests := []struct {
		name         string
		ifGeneration int64
		wantParam    string
	}{
		{"replace exactly that generation", 42, "42"},
		{"create only if absent", 0, "0"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			var got url.Values
			client, _ := testClient(t, func(w http.ResponseWriter, r *http.Request) {
				got = r.URL.Query()
				w.WriteHeader(http.StatusOK)
			})
			if err := client.PutObject(context.Background(), "zz-bucket", "lease.json",
				[]byte(`{}`), tc.ifGeneration); err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if got.Get("ifGenerationMatch") != tc.wantParam {
				t.Errorf("ifGenerationMatch: want %q, got %q", tc.wantParam, got.Get("ifGenerationMatch"))
			}
			if got.Get("name") != "lease.json" {
				t.Errorf("name: got %q", got.Get("name"))
			}
		})
	}
}

func TestPutObjectOmitsThePreconditionWhenAskedTo(t *testing.T) {
	// Negative means "unconditional", and nothing in the reaper uses it today.
	// The test exists so that a future caller has to pass a negative number on
	// purpose rather than discovering that 0 happens to mean something else.
	var got url.Values
	client, _ := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		got = r.URL.Query()
		w.WriteHeader(http.StatusOK)
	})
	if err := client.PutObject(context.Background(), "zz-bucket", "x.json", []byte(`{}`), -1); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if got.Has("ifGenerationMatch") {
		t.Errorf("unconditional write must not send a precondition: %q", got.Encode())
	}
}

func TestPutObjectReportsALostRaceDistinctly(t *testing.T) {
	for _, status := range []int{http.StatusPreconditionFailed, http.StatusConflict} {
		client, _ := testClient(t, func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(status)
		})
		err := client.PutObject(context.Background(), "zz-bucket", "lease.json", []byte(`{}`), 7)
		if !errors.Is(err, ErrPreconditionFailed) {
			t.Errorf("status %d: want ErrPreconditionFailed, got %v", status, err)
		}
	}
}

func TestSetNodePoolSizeSendsTheCountAsJSON(t *testing.T) {
	var body []byte
	var method, contentType string
	client, srv := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		method, contentType = r.Method, r.Header.Get("Content-Type")
		body = make([]byte, r.ContentLength)
		_, _ = r.Body.Read(body)
		w.WriteHeader(http.StatusOK)
	})

	if err := client.SetNodePoolSize(context.Background(), srv.URL+"/v1/x:setSize", 0); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if method != http.MethodPost {
		t.Errorf("method: %q", method)
	}
	if contentType != "application/json" {
		t.Errorf("content type: %q", contentType)
	}
	if want := `{"nodeCount":0}`; string(body) != want {
		t.Errorf("body: want %s, got %s", want, body)
	}
}

func TestTokenFailureIsReportedNotSwallowed(t *testing.T) {
	// A reaper that silently treats "no credentials" as "nothing to do" would
	// never stop the cluster and never say why.
	client := &Client{
		HTTP:  http.DefaultClient,
		Token: func(context.Context) (string, error) { return "", errors.New("no token") },
	}
	if _, _, err := client.GetObject(context.Background(), "zz-bucket", "lease.json"); err == nil {
		t.Error("want the token error to surface")
	}
}

// The pool's RUNNING size, which is what L2's first rule ("already at zero:
// nothing to do") reads. initialNodeCount is the creation-time constant from
// gke.tf and stays 0 however many nodes are up, so a size read from it makes L2
// wait forever on a woken pool. The running size is the target size of the
// pool's managed instance groups -- the same read the Google provider does for
// node_count.
func TestNodePoolSizeIsTheInstanceGroupTargetNotTheCreationCount(t *testing.T) {
	var poolPath string
	var igmAuth string
	var srvURL string
	client, srv := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		switch {
		case strings.Contains(r.URL.Path, "/nodePools/"):
			poolPath = r.URL.Path
			_, _ = w.Write([]byte(`{"initialNodeCount":0,"instanceGroupUrls":["` +
				srvURL + `/compute/v1/projects/zz-project/zones/zz-zone/instanceGroupManagers/gke-exe-main-grp"]}`))
		case strings.HasSuffix(r.URL.Path, "/instanceGroupManagers/gke-exe-main-grp"):
			igmAuth = r.Header.Get("Authorization")
			_, _ = w.Write([]byte(`{"targetSize":1}`))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	})
	srvURL = srv.URL

	size, err := client.NodePoolSize(context.Background(), "zz-project", "zz-zone", "exe", "main")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if size != 1 {
		t.Fatalf("size: want 1 (the instance group's target), got %d -- a creation-count read makes L2 treat a woken pool as asleep", size)
	}
	if want := "/v1/projects/zz-project/locations/zz-zone/clusters/exe/nodePools/main"; poolPath != want {
		t.Errorf("node pool path: want %q, got %q", want, poolPath)
	}
	if igmAuth != "Bearer test-token" {
		t.Errorf("instance group read must be authenticated, got %q", igmAuth)
	}
}

func TestNodePoolSizeIsZeroWhenEveryGroupTargetsZero(t *testing.T) {
	var srvURL string
	client, srv := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		if strings.Contains(r.URL.Path, "/nodePools/") {
			_, _ = w.Write([]byte(`{"initialNodeCount":1,"instanceGroupUrls":["` +
				srvURL + `/compute/v1/projects/p/zones/z/instanceGroupManagers/g"]}`))
			return
		}
		_, _ = w.Write([]byte(`{"targetSize":0}`))
	})
	srvURL = srv.URL

	size, err := client.NodePoolSize(context.Background(), "p", "z", "exe", "main")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if size != 0 {
		t.Fatalf("size: want 0, got %d", size)
	}
}

func TestNodePoolSizeReportsAnUnreadableGroup(t *testing.T) {
	var srvURL string
	client, srv := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		if strings.Contains(r.URL.Path, "/nodePools/") {
			_, _ = w.Write([]byte(`{"instanceGroupUrls":["` +
				srvURL + `/compute/v1/projects/p/zones/z/instanceGroupManagers/g"]}`))
			return
		}
		w.WriteHeader(http.StatusForbidden)
	})
	srvURL = srv.URL

	// An unreadable group is an error, never a size: reporting 0 here would be
	// "asleep" for a pool nobody could see.
	if _, err := client.NodePoolSize(context.Background(), "p", "z", "exe", "main"); err == nil {
		t.Fatal("a 403 on the instance group must be an error, not a size")
	}
}
