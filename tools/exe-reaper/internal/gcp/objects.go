package gcp

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"time"
)

// The snapshot GC's half of GCS (Phase 6 plan D11): every object under a
// prefix, and deleting one exactly as it was listed. Nothing else in the
// reaper lists or deletes objects.

// objectPageSize asks for pages as large as the API allows.
const objectPageSize = 1000

// maxObjectPages bounds one listing: at objectPageSize objects a page, far
// beyond any bucket this project holds.
const maxObjectPages = 10000

// Object is one object as listed: the generation a delete is conditional on,
// and the time it was last written.
type Object struct {
	Name       string
	Updated    time.Time
	Generation int64
}

// ListObjects is every object in the bucket whose name starts with prefix.
// It is all or nothing: a page that fails fails the whole listing, and so
// does an object without a usable generation or update time.
func (c *Client) ListObjects(ctx context.Context, bucket, prefix string) ([]Object, error) {
	var out []Object
	token := ""
	for range maxObjectPages {
		query := url.Values{
			"prefix":     {prefix},
			"maxResults": {strconv.Itoa(objectPageSize)},
			"fields":     {"items(name,updated,generation),nextPageToken"},
		}
		if token != "" {
			query.Set("pageToken", token)
		}
		var page struct {
			Items []struct {
				Name       string `json:"name"`
				Updated    string `json:"updated"`
				Generation string `json:"generation"`
			} `json:"items"`
			NextPageToken string `json:"nextPageToken"`
		}
		rawURL := fmt.Sprintf("%s/storage/v1/b/%s/o?%s", c.storage(), url.PathEscape(bucket), query.Encode())
		if err := c.getJSON(ctx, rawURL, &page); err != nil {
			return nil, fmt.Errorf("listing gs://%s/%s: %w", bucket, prefix, err)
		}
		for _, item := range page.Items {
			generation, err := strconv.ParseInt(item.Generation, 10, 64)
			if err != nil || generation <= 0 {
				return nil, fmt.Errorf("gs://%s/%s: generation %q: %w", bucket, item.Name, item.Generation, ErrNoGeneration)
			}
			updated, err := time.Parse(time.RFC3339Nano, item.Updated)
			if err != nil {
				return nil, fmt.Errorf("gs://%s/%s: update time %q: %w", bucket, item.Name, item.Updated, err)
			}
			out = append(out, Object{Name: item.Name, Updated: updated, Generation: generation})
		}
		if page.NextPageToken == "" {
			return out, nil
		}
		token = page.NextPageToken
	}
	return nil, fmt.Errorf("listing gs://%s/%s: still paging after %d pages", bucket, prefix, maxObjectPages)
}

// DeleteObject deletes an object only while it is still the generation that
// was listed. An object already gone is the goal holding, not an error; one
// rewritten since is ErrPreconditionFailed.
func (c *Client) DeleteObject(ctx context.Context, bucket, object string, generation int64) error {
	query := url.Values{"ifGenerationMatch": {strconv.FormatInt(generation, 10)}}
	rawURL := fmt.Sprintf("%s/storage/v1/b/%s/o/%s?%s",
		c.storage(), url.PathEscape(bucket), url.PathEscape(object), query.Encode())
	resp, err := c.do(ctx, http.MethodDelete, rawURL, nil, nil)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	switch resp.StatusCode {
	case http.StatusOK, http.StatusNoContent, http.StatusNotFound:
		return nil
	case http.StatusPreconditionFailed:
		return fmt.Errorf("gs://%s/%s: %w", bucket, object, ErrPreconditionFailed)
	default:
		return statusError(resp)
	}
}
