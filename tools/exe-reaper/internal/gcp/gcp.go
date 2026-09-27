// Package gcp is the thin I/O layer the reaper needs, over stdlib net/http.
//
// No cloud SDK, deliberately. What the reaper does with Google APIs is: read and
// conditionally write three small JSON objects in one GCS bucket, and POST one
// setSize call. That is three endpoints. Pulling in cloud.google.com/go/storage
// and the GKE client for it would add a large dependency tree to a binary whose
// entire job is to be trustworthy enough to stop a cluster, and the repo's
// stdlib-first rule points the same way.
//
// Tokens come from one of two places, tried in order: the metadata server (when
// running as the Cloud Run job or on a node), then GOOGLE_OAUTH_ACCESS_TOKEN
// (which `just` recipes fill from `gcloud auth print-access-token` for the
// operator's own path). No key files, no ADC file parsing.
package gcp

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"time"
)

// G101 below is a false positive twice over: the first is the metadata
// server's public endpoint, the second the NAME of an env var. Neither holds a
// credential; the token is fetched or read at run time.
const (
	metadataTokenURL = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" //nolint:gosec // G101: endpoint URL, not a credential
	tokenEnv         = "GOOGLE_OAUTH_ACCESS_TOKEN"                                                                  //nolint:gosec // G101: env var name, not a credential

	storageBase   = "https://storage.googleapis.com"
	containerBase = "https://container.googleapis.com"

	defaultTimeout = 30 * time.Second
)

// ErrNotFound is returned for a missing object, distinctly from a transport
// failure. The distinction is load-bearing: "the lease does not exist" means the
// cluster is not authorised, while "GCS did not answer" means try again -- and
// conflating them is how a transient error becomes a destroyed workspace.
var ErrNotFound = errors.New("object not found")

// ErrPreconditionFailed is returned when a conditional write lost the race.
var ErrPreconditionFailed = errors.New("generation precondition failed")

// Client is an authenticated HTTP client for the two APIs the reaper uses.
type Client struct {
	HTTP  *http.Client
	Token func(ctx context.Context) (string, error)
	// StorageBase overrides the GCS endpoint. Empty means the real one; the
	// tests point it at an httptest server. An injectable base is the smallest
	// seam that lets the URL, query parameters and status handling be tested for
	// real instead of re-asserted against a fake of my own writing.
	StorageBase string
	// ContainerBase overrides the GKE endpoint, for the same reason.
	ContainerBase string
}

func (c *Client) storage() string {
	if c.StorageBase != "" {
		return c.StorageBase
	}
	return storageBase
}

func (c *Client) container() string {
	if c.ContainerBase != "" {
		return c.ContainerBase
	}
	return containerBase
}

// New returns a Client with the default token chain.
func New() *Client {
	return &Client{
		HTTP:  &http.Client{Timeout: defaultTimeout},
		Token: defaultToken,
	}
}

func defaultToken(ctx context.Context) (string, error) {
	// Metadata server first: inside Cloud Run or on a node this is the identity
	// that matters, and it needs no configuration.
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, metadataTokenURL, nil)
	if err == nil {
		req.Header.Set("Metadata-Flavor", "Google")
		client := &http.Client{Timeout: 2 * time.Second}
		if resp, err := client.Do(req); err == nil {
			defer func() { _ = resp.Body.Close() }()
			if resp.StatusCode == http.StatusOK {
				var payload struct {
					AccessToken string `json:"access_token"`
				}
				if err := json.NewDecoder(resp.Body).Decode(&payload); err == nil && payload.AccessToken != "" {
					return payload.AccessToken, nil
				}
			}
		}
	}
	if tok := os.Getenv(tokenEnv); tok != "" {
		return tok, nil
	}
	return "", fmt.Errorf("no access token: metadata server unavailable and $%s is empty", tokenEnv)
}

func (c *Client) do(ctx context.Context, method, rawURL string, body []byte, headers map[string]string) (*http.Response, error) {
	token, err := c.Token(ctx)
	if err != nil {
		return nil, err
	}
	var reader io.Reader
	if body != nil {
		reader = bytes.NewReader(body)
	}
	req, err := http.NewRequestWithContext(ctx, method, rawURL, reader)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+token)
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	return c.HTTP.Do(req)
}

// GetObject reads an object and returns its body and generation.
//
// The generation is not a detail: every write the reaper makes is conditional on
// it, which is what enforces "one writer per object" against two processes that
// both believe they are that writer.
func (c *Client) GetObject(ctx context.Context, bucket, object string) (data []byte, generation int64, err error) {
	rawURL := fmt.Sprintf("%s/storage/v1/b/%s/o/%s?alt=media",
		c.storage(), url.PathEscape(bucket), url.PathEscape(object))
	resp, err := c.do(ctx, http.MethodGet, rawURL, nil, nil)
	if err != nil {
		return nil, 0, err
	}
	defer func() { _ = resp.Body.Close() }()

	switch resp.StatusCode {
	case http.StatusOK:
	case http.StatusNotFound:
		return nil, 0, fmt.Errorf("%s/%s: %w", bucket, object, ErrNotFound)
	default:
		return nil, 0, statusError(resp)
	}

	data, err = io.ReadAll(resp.Body)
	if err != nil {
		return nil, 0, err
	}
	// The media download carries the generation in a header, which saves a
	// second metadata request per read -- and the reaper reads on every tick.
	generation, _ = strconv.ParseInt(resp.Header.Get("X-Goog-Generation"), 10, 64)
	return data, generation, nil
}

// PutObject writes an object conditionally.
//
// ifGeneration semantics, which are the whole point:
//
//	>0  replace exactly that generation (optimistic concurrency)
//	 0  create only if absent
//	<0  unconditional (used by nothing in the reaper today; kept so the one
//	    caller that ever needs it has to say so explicitly)
func (c *Client) PutObject(ctx context.Context, bucket, object string, data []byte, ifGeneration int64) error {
	query := url.Values{
		"uploadType": {"media"},
		"name":       {object},
	}
	if ifGeneration >= 0 {
		query.Set("ifGenerationMatch", strconv.FormatInt(ifGeneration, 10))
	}
	rawURL := fmt.Sprintf("%s/upload/storage/v1/b/%s/o?%s",
		c.storage(), url.PathEscape(bucket), query.Encode())

	resp, err := c.do(ctx, http.MethodPost, rawURL, data,
		map[string]string{"Content-Type": "application/json"})
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	switch resp.StatusCode {
	case http.StatusOK, http.StatusCreated:
		return nil
	case http.StatusPreconditionFailed, http.StatusConflict:
		return fmt.Errorf("%s/%s: %w", bucket, object, ErrPreconditionFailed)
	default:
		return statusError(resp)
	}
}

// SetNodePoolSize calls nodePools.setSize.
//
// The URI is passed in rather than assembled here, so that exactly one place in
// the whole system decides which pool is resized: the OpenTofu stack builds it
// from the cluster and node-pool resources and hands it to both L2 (as an env
// var) and L3 (as the Scheduler target). A reaper that assembled its own URI
// could disagree with the Scheduler about which pool to stop.
func (c *Client) SetNodePoolSize(ctx context.Context, setSizeURI string, size int) error {
	body, err := json.Marshal(map[string]int{"nodeCount": size})
	if err != nil {
		return err
	}
	resp, err := c.do(ctx, http.MethodPost, setSizeURI, body,
		map[string]string{"Content-Type": "application/json"})
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()

	if resp.StatusCode != http.StatusOK {
		return statusError(resp)
	}
	return nil
}

// NodePoolSize reads the pool's RUNNING size: the summed target size of its
// managed instance groups.
//
// Not initialNodeCount. That field is the creation-time constant gke.tf sets
// (0) and it does not move when the pool is resized, so reading it reports
// "asleep" for a pool with a node up -- and L2's first rule, "already at zero:
// nothing to do", would then never stop anything. The instance groups are what
// setSize actually changes, and summing their target sizes is the same read the
// Google provider does for a pool's node_count. The target, not the live
// instance count: after setSize(0) the target is 0 at once while the VM is still
// being deleted, and a stop already under way needs nothing more from L2.
//
// The group URLs come from the node pool itself, so no instance group name is
// guessed here. Any unreadable group is an error, never a size.
func (c *Client) NodePoolSize(ctx context.Context, project, zone, cluster, pool string) (int, error) {
	rawURL := fmt.Sprintf("%s/v1/projects/%s/locations/%s/clusters/%s/nodePools/%s",
		c.container(), url.PathEscape(project), url.PathEscape(zone),
		url.PathEscape(cluster), url.PathEscape(pool))
	var np struct {
		InstanceGroupUrls []string `json:"instanceGroupUrls"`
	}
	if err := c.getJSON(ctx, rawURL, &np); err != nil {
		return 0, fmt.Errorf("node pool %s: %w", pool, err)
	}

	total := 0
	for _, groupURL := range np.InstanceGroupUrls {
		var igm struct {
			TargetSize int `json:"targetSize"`
		}
		if err := c.getJSON(ctx, groupURL, &igm); err != nil {
			return 0, fmt.Errorf("instance group of node pool %s: %w", pool, err)
		}
		total += igm.TargetSize
	}
	return total, nil
}

// getJSON GETs a Google API resource and decodes it, keeping 404 distinct.
func (c *Client) getJSON(ctx context.Context, rawURL string, into any) error {
	resp, err := c.do(ctx, http.MethodGet, rawURL, nil, nil)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode == http.StatusNotFound {
		return ErrNotFound
	}
	if resp.StatusCode != http.StatusOK {
		return statusError(resp)
	}
	return json.NewDecoder(resp.Body).Decode(into)
}

func statusError(resp *http.Response) error {
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 2048))
	// The body can contain the project id, so it is included only at the one
	// call site that prints to the operator's own terminal; callers that log to
	// a shared place should wrap this.
	return fmt.Errorf("%s %s: %s", resp.Request.Method, resp.Request.URL.Path, bytes.TrimSpace(body))
}
