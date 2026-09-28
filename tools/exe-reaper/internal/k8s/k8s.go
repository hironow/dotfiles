// Package k8s is the little of the Kubernetes API L1 needs, spoken over plain
// net/http: the scale subresource of the two Deployments whose replica counts
// L1 owns (atenet-router and ax-controller, plan D2), a count of the pods that
// can still run behind them, the images the cluster's own pods run (which
// retention keeps tagged, M19 C3), and deleting a wedged worker's pod (plan
// D6).
//
// Stdlib only, like internal/gcp: client-go would be the whole dependency tree
// of Kubernetes for five requests. Every request authenticates with the pod's
// projected service-account token, read from its file each time because the
// kubelet rotates it in place, and verifies the API server against the
// cluster CA mounted beside it.
package k8s

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"maps"
	"net"
	"net/http"
	"net/url"
	"os"
	"slices"
	"strconv"
	"strings"
	"time"
)

const (
	serviceAccountDir = "/var/run/secrets/kubernetes.io/serviceaccount"

	requestTimeout = 20 * time.Second

	// podPage bounds one list response; a continue token carries the rest.
	podPage = 500
)

// ErrPodReplaced is a delete refused because the pod under that name is no
// longer the one it was asked for: a new pod reused the name.
var ErrPodReplaced = errors.New("the pod under that name is a different pod now")

// Config says where the API server is and how to trust and authenticate to it.
type Config struct {
	// Host is the API server's base URL, https://host:port.
	Host string
	// CAFile verifies the API server.
	CAFile string
	// TokenFile holds the bearer token, read on every request.
	TokenFile string
}

// Client talks to one API server.
type Client struct {
	host      string
	tokenFile string
	http      *http.Client
}

// InCluster is the Config every pod is given: the API server from the service
// environment, and the service account's CA and token.
func InCluster() (*Client, error) {
	host, port := os.Getenv("KUBERNETES_SERVICE_HOST"), os.Getenv("KUBERNETES_SERVICE_PORT")
	if host == "" || port == "" {
		return nil, errors.New("not in a cluster: KUBERNETES_SERVICE_HOST / _PORT are unset")
	}
	return New(Config{
		Host:      "https://" + net.JoinHostPort(host, port),
		CAFile:    serviceAccountDir + "/ca.crt",
		TokenFile: serviceAccountDir + "/token",
	})
}

// New returns a client for cfg.
func New(cfg Config) (*Client, error) {
	pemBytes, err := os.ReadFile(cfg.CAFile)
	if err != nil {
		return nil, fmt.Errorf("reading the cluster CA: %w", err)
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(pemBytes) {
		return nil, fmt.Errorf("%s holds no PEM certificate", cfg.CAFile)
	}
	return &Client{
		host:      strings.TrimSuffix(cfg.Host, "/"),
		tokenFile: cfg.TokenFile,
		http: &http.Client{
			Timeout: requestTimeout,
			Transport: &http.Transport{
				TLSClientConfig: &tls.Config{RootCAs: roots, MinVersion: tls.VersionTLS12},
			},
		},
	}, nil
}

// scale is the autoscaling/v1 Scale object, the parts L1 reads.
type scale struct {
	Spec struct {
		Replicas int `json:"replicas"`
	} `json:"spec"`
	Status struct {
		Selector string `json:"selector"`
	} `json:"status"`
}

func scalePath(ns, deployment string) string {
	return "/apis/apps/v1/namespaces/" + url.PathEscape(ns) + "/deployments/" + url.PathEscape(deployment) + "/scale"
}

// Scale reads a Deployment's replica count, and the label selector of its
// pods as the scale subresource reports it.
func (c *Client) Scale(ctx context.Context, ns, deployment string) (int, string, error) {
	var s scale
	if err := c.call(ctx, http.MethodGet, scalePath(ns, deployment), "", nil, &s); err != nil {
		return 0, "", fmt.Errorf("reading the scale of %s/%s: %w", ns, deployment, err)
	}
	return s.Spec.Replicas, s.Status.Selector, nil
}

// SetScale sets a Deployment's replica count, and nothing else: a merge patch
// of spec.replicas on the scale subresource.
func (c *Client) SetScale(ctx context.Context, ns, deployment string, replicas int) error {
	body := []byte(`{"spec":{"replicas":` + strconv.Itoa(replicas) + `}}`)
	if err := c.call(ctx, http.MethodPatch, scalePath(ns, deployment), "application/merge-patch+json", body, nil); err != nil {
		return fmt.Errorf("scaling %s/%s to %d: %w", ns, deployment, replicas, err)
	}
	return nil
}

type podList struct {
	Items []struct {
		Spec struct {
			Containers     []containerSpec `json:"containers"`
			InitContainers []containerSpec `json:"initContainers"`
		} `json:"spec"`
		Status struct {
			Phase                 string            `json:"phase"`
			ContainerStatuses     []containerStatus `json:"containerStatuses"`
			InitContainerStatuses []containerStatus `json:"initContainerStatuses"`
		} `json:"status"`
	} `json:"items"`
	Metadata struct {
		Continue string `json:"continue"`
	} `json:"metadata"`
}

type containerSpec struct {
	Image string `json:"image"`
}

type containerStatus struct {
	ImageID string `json:"imageID"`
}

// CountPods counts the pods matching selector that can still run: every pod
// but a Succeeded or Failed one. A terminating pod counts until it is gone,
// because it serves until then (plan D2 step 6).
func (c *Client) CountPods(ctx context.Context, ns, selector string) (int, error) {
	if selector == "" {
		return 0, errors.New("counting pods with an empty selector would count the whole namespace")
	}
	n := 0
	cont := ""
	for {
		q := url.Values{"labelSelector": {selector}, "limit": {strconv.Itoa(podPage)}}
		if cont != "" {
			q.Set("continue", cont)
		}
		var list podList
		if err := c.call(ctx, http.MethodGet, "/api/v1/namespaces/"+url.PathEscape(ns)+"/pods?"+q.Encode(), "", nil, &list); err != nil {
			return 0, fmt.Errorf("listing pods in %s (%s): %w", ns, selector, err)
		}
		for _, p := range list.Items {
			if p.Status.Phase != "Succeeded" && p.Status.Phase != "Failed" {
				n++
			}
		}
		if list.Metadata.Continue == "" {
			return n, nil
		}
		cont = list.Metadata.Continue
	}
}

// PodImages lists the images the pods in ns run or are about to run, each a
// reference pinned by digest, sorted and without repeats: every started
// container's image as its status resolved it (the digest the node pulled,
// even when the spec names a tag), and every spec image already pinned by
// digest, which is all a pod that has not started has. Init containers count
// too. An image with no repository, one the node built or loaded itself, is
// left out: no registry holds it.
func (c *Client) PodImages(ctx context.Context, ns string) ([]string, error) {
	seen := map[string]bool{}
	add := func(ref string) {
		// Docker-era runtimes prefix the ID with a scheme.
		if _, rest, ok := strings.Cut(ref, "://"); ok {
			ref = rest
		}
		if name, _, ok := strings.Cut(ref, "@sha256:"); ok && name != "" {
			seen[ref] = true
		}
	}
	cont := ""
	for {
		q := url.Values{"limit": {strconv.Itoa(podPage)}}
		if cont != "" {
			q.Set("continue", cont)
		}
		var list podList
		if err := c.call(ctx, http.MethodGet, "/api/v1/namespaces/"+url.PathEscape(ns)+"/pods?"+q.Encode(), "", nil, &list); err != nil {
			return nil, fmt.Errorf("listing pods in %s: %w", ns, err)
		}
		for _, p := range list.Items {
			for _, s := range slices.Concat(p.Status.ContainerStatuses, p.Status.InitContainerStatuses) {
				add(s.ImageID)
			}
			for _, s := range slices.Concat(p.Spec.Containers, p.Spec.InitContainers) {
				add(s.Image)
			}
		}
		if list.Metadata.Continue == "" {
			return slices.Sorted(maps.Keys(seen)), nil
		}
		cont = list.Metadata.Continue
	}
}

// DeletePod deletes one pod, but only while it is still the pod with that UID.
// A pod already gone is success: the delete's goal holds. A different pod
// under the same name is ErrPodReplaced.
func (c *Client) DeletePod(ctx context.Context, ns, name, uid string) error {
	body, err := json.Marshal(map[string]any{
		"kind":          "DeleteOptions",
		"apiVersion":    "v1",
		"preconditions": map[string]string{"uid": uid},
	})
	if err != nil {
		return err
	}
	err = c.call(ctx, http.MethodDelete, "/api/v1/namespaces/"+url.PathEscape(ns)+"/pods/"+url.PathEscape(name), "application/json", body, nil)
	var status *StatusError
	switch {
	case err == nil:
		return nil
	case errors.As(err, &status) && status.Code == http.StatusNotFound:
		return nil
	case errors.As(err, &status) && status.Code == http.StatusConflict:
		return fmt.Errorf("deleting pod %s/%s (uid %s): %w", ns, name, uid, ErrPodReplaced)
	default:
		return fmt.Errorf("deleting pod %s/%s: %w", ns, name, err)
	}
}

// StatusError is an answer outside 2xx, with the start of its body.
type StatusError struct {
	Code int
	Body string
}

func (e *StatusError) Error() string {
	return fmt.Sprintf("%d %s: %s", e.Code, http.StatusText(e.Code), e.Body)
}

// call makes one request and decodes a 2xx answer into out (when out is
// non-nil).
func (c *Client) call(ctx context.Context, method, path, contentType string, body []byte, out any) error {
	token, err := os.ReadFile(c.tokenFile)
	if err != nil {
		return fmt.Errorf("reading the service-account token: %w", err)
	}
	var reader io.Reader
	if body != nil {
		reader = bytes.NewReader(body)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.host+path, reader)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+strings.TrimSpace(string(token)))
	req.Header.Set("Accept", "application/json")
	if contentType != "" {
		req.Header.Set("Content-Type", contentType)
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()
	if resp.StatusCode < 200 || resp.StatusCode > 299 {
		snippet, _ := io.ReadAll(io.LimitReader(resp.Body, 512))
		return &StatusError{Code: resp.StatusCode, Body: strings.TrimSpace(string(snippet))}
	}
	if out == nil {
		return nil
	}
	return json.NewDecoder(resp.Body).Decode(out)
}
