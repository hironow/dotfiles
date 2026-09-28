package gcp

import (
	"context"
	"errors"
	"net/http"
	"net/url"
	"slices"
	"strings"
	"testing"
	"time"
)

// The snapshot GC's half of GCS (plan D11): every object under a prefix, and
// deleting one exactly as it was listed. Same approach as the tests above: an
// httptest server, so the real URLs, escaping, pagination and status handling
// run.

func TestListObjectsReadsEveryPageUnderThePrefix(t *testing.T) {
	// given two pages of objects under ax/atespaces/
	var queries []url.Values
	client, _ := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.URL.Path != "/storage/v1/b/zz-snap/o" {
			http.Error(w, "unexpected "+r.Method+" "+r.URL.Path, http.StatusNotFound)
			return
		}
		queries = append(queries, r.URL.Query())
		switch r.URL.Query().Get("pageToken") {
		case "":
			_, _ = w.Write([]byte(`{"items":[{"name":"ax/atespaces/exe/actors/u1/snapshots/s1/manifest","updated":"2026-09-01T10:00:00.123Z","generation":"1756720800123456"}],"nextPageToken":"p2"}`))
		case "p2":
			_, _ = w.Write([]byte(`{"items":[{"name":"ax/atespaces/exe/actors/u2/x","updated":"2026-09-02T10:00:00Z","generation":"7"}]}`))
		default:
			http.Error(w, "bad page token", http.StatusBadRequest)
		}
	})

	// when
	got, err := client.ListObjects(context.Background(), "zz-snap", "ax/atespaces/")
	// then every object of both pages, with the generation a delete names and
	// the time the age rule reads
	if err != nil {
		t.Fatal(err)
	}
	want := []Object{
		{Name: "ax/atespaces/exe/actors/u1/snapshots/s1/manifest", Updated: time.Date(2026, 9, 1, 10, 0, 0, 123e6, time.UTC), Generation: 1756720800123456},
		{Name: "ax/atespaces/exe/actors/u2/x", Updated: time.Date(2026, 9, 2, 10, 0, 0, 0, time.UTC), Generation: 7},
	}
	if !slices.EqualFunc(got, want, func(a, b Object) bool {
		return a.Name == b.Name && a.Updated.Equal(b.Updated) && a.Generation == b.Generation
	}) {
		t.Errorf("objects:\n got %+v\nwant %+v", got, want)
	}
	// and every page was asked for under the prefix
	if len(queries) != 2 {
		t.Fatalf("%d requests, want 2", len(queries))
	}
	for _, q := range queries {
		if q.Get("prefix") != "ax/atespaces/" {
			t.Errorf("a page was listed under prefix %q", q.Get("prefix"))
		}
	}
}

func TestListObjectsIsAllOrNothing(t *testing.T) {
	// given a second page that fails
	client, _ := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("pageToken") == "" {
			_, _ = w.Write([]byte(`{"items":[{"name":"ax/atespaces/exe/actors/u1/x","updated":"2026-09-01T10:00:00Z","generation":"1"}],"nextPageToken":"p2"}`))
			return
		}
		http.Error(w, "backend error", http.StatusServiceUnavailable)
	})

	// when
	got, err := client.ListObjects(context.Background(), "zz-snap", "ax/atespaces/")
	// then no partial list: a GC that saw half the bucket would still be right
	// to delete what it saw, but a caller must not mistake half for all
	if err == nil {
		t.Errorf("a failed page reported success, with %d objects", len(got))
	}
}

// A delete names the generation it was listed at, and the age rule reads the
// update time, so an object without either is not one the GC can reason about.
func TestListObjectsRefusesAnObjectWithoutAGenerationOrATime(t *testing.T) {
	for name, item := range map[string]string{
		"no generation":      `{"name":"a","updated":"2026-09-01T10:00:00Z"}`,
		"garbled generation": `{"name":"a","updated":"2026-09-01T10:00:00Z","generation":"x"}`,
		"no time":            `{"name":"a","generation":"1"}`,
	} {
		t.Run(name, func(t *testing.T) {
			client, _ := testClient(t, func(w http.ResponseWriter, _ *http.Request) {
				_, _ = w.Write([]byte(`{"items":[` + item + `]}`))
			})
			if _, err := client.ListObjects(context.Background(), "zz-snap", ""); err == nil {
				t.Error("an unusable object was listed")
			}
		})
	}
}

func TestDeleteObjectDeletesExactlyTheListedGeneration(t *testing.T) {
	// given
	var method, path, match string
	client, _ := testClient(t, func(w http.ResponseWriter, r *http.Request) {
		method, path, match = r.Method, r.URL.EscapedPath(), r.URL.Query().Get("ifGenerationMatch")
		w.WriteHeader(http.StatusNoContent)
	})

	// when
	err := client.DeleteObject(context.Background(), "zz-snap", "ax/atespaces/exe/actors/u1/x", 7)
	// then one DELETE of that object, its slashes escaped so they stay part of
	// its name, and only if it is still the generation that was listed
	if err != nil {
		t.Fatal(err)
	}
	if method != http.MethodDelete || path != "/storage/v1/b/zz-snap/o/ax%2Fatespaces%2Fexe%2Factors%2Fu1%2Fx" {
		t.Errorf("request %s %s", method, path)
	}
	if match != "7" {
		t.Errorf("ifGenerationMatch %q, want 7", match)
	}
}

func TestDeleteObjectOfAnObjectAlreadyGoneIsFine(t *testing.T) {
	client, _ := testClient(t, func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "No such object", http.StatusNotFound)
	})
	if err := client.DeleteObject(context.Background(), "zz-snap", "a", 1); err != nil {
		t.Errorf("deleting an object that is gone: %v", err)
	}
}

// Rewritten since it was listed: whatever wrote it is alive, and the GC must
// not have the last word.
func TestDeleteObjectOfARewrittenObjectIsAPreconditionFailure(t *testing.T) {
	client, _ := testClient(t, func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "conditionNotMet", http.StatusPreconditionFailed)
	})
	err := client.DeleteObject(context.Background(), "zz-snap", "a", 1)
	if !errors.Is(err, ErrPreconditionFailed) {
		t.Errorf("err %v, want ErrPreconditionFailed", err)
	}
}

func TestAnyOtherDeleteFailureIsAnError(t *testing.T) {
	client, _ := testClient(t, func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "denied", http.StatusForbidden)
	})
	err := client.DeleteObject(context.Background(), "zz-snap", "a", 1)
	if err == nil || errors.Is(err, ErrPreconditionFailed) || !strings.Contains(err.Error(), "denied") {
		t.Errorf("err %v, want the refusal", err)
	}
}
