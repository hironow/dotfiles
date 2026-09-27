package gcp

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"net/url"
	"slices"
	"strings"
	"sync"
	"sync/atomic"
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

// A 200 that cannot say which generation it read is an error, never a
// generation. Every conditional write and every drain comparison keys on the
// generation, and the values a missing or garbled header would silently turn
// into already mean something: to PutObject, 0 is "create only if absent" and a
// negative number is "unconditional". Not ErrNotFound either: the object is
// there, and reading it as absent tells L2 the lease was deleted.
func TestGetObjectRefusesAReadWithoutAUsableGeneration(t *testing.T) {
	tests := []struct {
		name       string
		generation string // "" leaves the header out
	}{
		{"no header", ""},
		{"garbled", "not-a-generation"},
		{"zero, which PutObject would take as create-only", "0"},
		{"negative, which PutObject would take as unconditional", "-5"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			client, _ := testClient(t, func(w http.ResponseWriter, _ *http.Request) {
				if tc.generation != "" {
					w.Header().Set("X-Goog-Generation", tc.generation)
				}
				_, _ = w.Write([]byte(`{"deadline":"2026-09-27T12:00:00Z"}`))
			})

			_, generation, err := client.GetObject(context.Background(), "zz-bucket", "lease.json")
			if err == nil {
				t.Fatalf("want an error, got generation %d and no error", generation)
			}
			if !errors.Is(err, ErrNoGeneration) {
				t.Errorf("want errors.Is(..., ErrNoGeneration); got %v", err)
			}
			if errors.Is(err, ErrNotFound) {
				t.Errorf("the object is there; an unusable generation must not read as ErrNotFound: %v", err)
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

// The default token chain, against a stand-in metadata server. Each fetch
// hands out a new token (meta-token-1, meta-token-2, ...), so a test can tell a
// cached token from a refreshed one, and every request is counted, so a test
// can prove the server was never asked. Like the real server, it refuses a
// request without Metadata-Flavor: Google.
func metadataServer(t *testing.T, expiresIn int) (*httptest.Server, *atomic.Int32) {
	t.Helper()
	var requests atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := requests.Add(1)
		if r.Header.Get("Metadata-Flavor") != "Google" {
			w.WriteHeader(http.StatusForbidden)
			return
		}
		_, _ = fmt.Fprintf(w, `{"access_token":"meta-token-%d","expires_in":%d,"token_type":"Bearer"}`, n, expiresIn)
	}))
	t.Cleanup(srv.Close)
	return srv, &requests
}

// tokenClient is a Client on the default token chain, pointed at the given
// metadata endpoint and at a storage server that records the Authorization
// header of every request it serves.
func tokenClient(t *testing.T, metadataURL string) (client *Client, auths func() []string) {
	t.Helper()
	var mu sync.Mutex
	var seen []string
	storage := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		seen = append(seen, r.Header.Get("Authorization"))
		mu.Unlock()
		w.Header().Set("X-Goog-Generation", "1")
		_, _ = w.Write([]byte(`{}`))
	}))
	t.Cleanup(storage.Close)
	tokens := &tokenSource{metadataURL: metadataURL}
	client = &Client{HTTP: storage.Client(), Token: tokens.Token, StorageBase: storage.URL}
	return client, func() []string {
		mu.Lock()
		defer mu.Unlock()
		return slices.Clone(seen)
	}
}

func getTwice(t *testing.T, client *Client) {
	t.Helper()
	for range 2 {
		if _, _, err := client.GetObject(context.Background(), "zz-bucket", "lease.json"); err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
	}
}

// Env first. $GOOGLE_OAUTH_ACCESS_TOKEN is set only where someone meant it to
// be (the just recipes fill it from gcloud for the operator), so when it is set
// the metadata server is not asked at all. Asked first, off GCP, it would cost
// up to a 2 s timeout on every request.
func TestTokenUsesTheEnvVarWithoutAskingTheMetadataServer(t *testing.T) {
	t.Setenv(tokenEnv, "env-token")
	meta, requests := metadataServer(t, 3600)
	client, auths := tokenClient(t, meta.URL)

	getTwice(t, client)

	if got, want := auths(), []string{"Bearer env-token", "Bearer env-token"}; !slices.Equal(got, want) {
		t.Errorf("authorization: want %q, got %q", want, got)
	}
	if n := requests.Load(); n != 0 {
		t.Errorf("metadata server asked %d time(s) with $%s set; want 0", n, tokenEnv)
	}
}

func TestTokenFallsBackToTheMetadataServerWhenTheEnvVarIsEmpty(t *testing.T) {
	// Set to empty rather than left alone: the operator's shell may export it.
	t.Setenv(tokenEnv, "")
	meta, _ := metadataServer(t, 3600)
	client, auths := tokenClient(t, meta.URL)

	if _, _, err := client.GetObject(context.Background(), "zz-bucket", "lease.json"); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if got, want := auths(), []string{"Bearer meta-token-1"}; !slices.Equal(got, want) {
		t.Errorf("authorization: want %q, got %q", want, got)
	}
}

// One metadata fetch per token lifetime, not one per request: an L2 tick makes
// half a dozen requests.
func TestMetadataTokenIsCachedAcrossRequests(t *testing.T) {
	t.Setenv(tokenEnv, "")
	meta, requests := metadataServer(t, 3600)
	client, auths := tokenClient(t, meta.URL)

	getTwice(t, client)

	if got, want := auths(), []string{"Bearer meta-token-1", "Bearer meta-token-1"}; !slices.Equal(got, want) {
		t.Errorf("authorization: want %q, got %q", want, got)
	}
	if n := requests.Load(); n != 1 {
		t.Errorf("metadata fetches for two requests: want 1, got %d", n)
	}
}

// expires_in is honoured: a token in the last minute of its life is replaced
// rather than presented, since a request that outlives the token fails.
func TestMetadataTokenNearItsExpiryIsRefreshed(t *testing.T) {
	t.Setenv(tokenEnv, "")
	meta, requests := metadataServer(t, 30) // already inside the last minute
	client, auths := tokenClient(t, meta.URL)

	getTwice(t, client)

	if got, want := auths(), []string{"Bearer meta-token-1", "Bearer meta-token-2"}; !slices.Equal(got, want) {
		t.Errorf("authorization: want %q, got %q", want, got)
	}
	if n := requests.Load(); n != 2 {
		t.Errorf("metadata fetches: want 2, got %d", n)
	}
}

// The cache is shared by every request a Client makes, so it has to hold under
// concurrent first use: one fetch between all the callers, one token for all.
func TestConcurrentFirstUseFetchesTheMetadataTokenOnce(t *testing.T) {
	t.Setenv(tokenEnv, "")
	meta, requests := metadataServer(t, 3600)
	tokens := &tokenSource{metadataURL: meta.URL}

	const callers = 8
	got := make([]string, callers)
	errs := make([]error, callers)
	var wg sync.WaitGroup
	for i := range callers {
		wg.Go(func() { got[i], errs[i] = tokens.Token(context.Background()) })
	}
	wg.Wait()

	for i := range callers {
		if errs[i] != nil || got[i] != "meta-token-1" {
			t.Errorf("caller %d: got %q, %v; want meta-token-1", i, got[i], errs[i])
		}
	}
	if n := requests.Load(); n != 1 {
		t.Errorf("metadata fetches for %d concurrent first calls: want 1, got %d", callers, n)
	}
}

// No env var and no metadata token is an error, and one that names the env
// var: on the operator's Mac that is the one thing there is to fix.
func TestNoTokenAnywhereIsAClearError(t *testing.T) {
	tests := []struct {
		name    string
		handler http.HandlerFunc // nil: nothing is listening
	}{
		{"metadata server unreachable", nil},
		{"metadata server refuses", func(w http.ResponseWriter, _ *http.Request) {
			w.WriteHeader(http.StatusForbidden)
		}},
		{"metadata server answers without a token", func(w http.ResponseWriter, _ *http.Request) {
			_, _ = w.Write([]byte(`{"expires_in":3600}`))
		}},
		{"metadata server answers garbage", func(w http.ResponseWriter, _ *http.Request) {
			_, _ = w.Write([]byte(`<html>`))
		}},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Setenv(tokenEnv, "")
			srv := httptest.NewServer(tc.handler)
			if tc.handler == nil {
				srv.Close() // a closed server's URL refuses connections
			} else {
				t.Cleanup(srv.Close)
			}

			tok, err := (&tokenSource{metadataURL: srv.URL}).Token(context.Background())
			if err == nil {
				t.Fatalf("want an error, got token %q", tok)
			}
			if !strings.Contains(err.Error(), tokenEnv) {
				t.Errorf("the error should name $%s: %v", tokenEnv, err)
			}
		})
	}
}

// New wires that chain in: with the env var set, New's Client authenticates
// with the env token.
func TestNewAuthenticatesWithTheEnvToken(t *testing.T) {
	t.Setenv(tokenEnv, "env-token")
	var mu sync.Mutex
	var gotAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		gotAuth = r.Header.Get("Authorization")
		mu.Unlock()
		w.Header().Set("X-Goog-Generation", "1")
		_, _ = w.Write([]byte(`{}`))
	}))
	t.Cleanup(srv.Close)

	client := New()
	client.StorageBase = srv.URL
	if _, _, err := client.GetObject(context.Background(), "zz-bucket", "lease.json"); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	mu.Lock()
	defer mu.Unlock()
	if gotAuth != "Bearer env-token" {
		t.Errorf("authorization: want %q, got %q", "Bearer env-token", gotAuth)
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

// The detector L2 runs (inbox M18, layer 3) needs what is really there, not
// only what was asked for: the target reads zero the moment setSize(0) is
// accepted, while the VM is still being deleted and still bills. The same
// instance group GET carries currentActions -- one count per action, every
// instance in the group counted once -- so reading it needs no new permission.
func TestNodePoolReportsTheInstancesStillThere(t *testing.T) {
	tests := []struct {
		name string
		igms []string
		want Pool
	}{
		{"a live pool", []string{`{"targetSize":1,"currentActions":{"none":1}}`}, Pool{Target: 1, Instances: 1}},
		{"stopping: the target is zero, the VM is still being deleted", []string{`{"targetSize":0,"currentActions":{"deleting":1,"none":0}}`}, Pool{Target: 0, Instances: 1}},
		{"gone", []string{`{"targetSize":0,"currentActions":{"none":0,"deleting":0}}`}, Pool{Target: 0, Instances: 0}},
		{"every action counts", []string{`{"targetSize":1,"currentActions":{"creating":1,"verifying":1}}`}, Pool{Target: 1, Instances: 2}},
		{"groups add up", []string{`{"targetSize":1,"currentActions":{"none":1}}`, `{"targetSize":0,"currentActions":{"deleting":1}}`}, Pool{Target: 1, Instances: 2}},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			var srvURL string
			client, srv := testClient(t, func(w http.ResponseWriter, r *http.Request) {
				if strings.Contains(r.URL.Path, "/nodePools/") {
					var urls []string
					for i := range tc.igms {
						urls = append(urls, fmt.Sprintf("%q", fmt.Sprintf("%s/compute/v1/projects/p/zones/z/instanceGroupManagers/g%d", srvURL, i)))
					}
					_, _ = fmt.Fprintf(w, `{"instanceGroupUrls":[%s]}`, strings.Join(urls, ","))
					return
				}
				var i int
				if _, err := fmt.Sscanf(r.URL.Path[strings.LastIndex(r.URL.Path, "/g")+2:], "%d", &i); err != nil || i >= len(tc.igms) {
					w.WriteHeader(http.StatusNotFound)
					return
				}
				_, _ = w.Write([]byte(tc.igms[i]))
			})
			srvURL = srv.URL

			got, err := client.NodePool(context.Background(), "p", "z", "exe", "main")
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if got != tc.want {
				t.Errorf("want %+v, got %+v", tc.want, got)
			}
		})
	}
}
