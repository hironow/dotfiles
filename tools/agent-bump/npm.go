package main

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"slices"
	"strings"
	"time"

	json "github.com/goccy/go-json/v2"
)

// npmRegistry is the Registry adapter for registry.npmjs.org.
type npmRegistry struct {
	client *http.Client
	base   string
}

func newNpmRegistry() *npmRegistry {
	return &npmRegistry{client: &http.Client{Timeout: 30 * time.Second}, base: "https://registry.npmjs.org"}
}

func (n *npmRegistry) Versions(ctx context.Context, pkg string) (string, []string, error) {
	// A scoped name keeps its @ and encodes the slash: @scope%2Fname.
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, n.base+"/"+strings.Replace(pkg, "/", "%2F", 1), nil)
	if err != nil {
		return "", nil, err
	}
	req.Header.Set("Accept", "application/vnd.npm.install-v1+json") // the short form
	resp, err := n.client.Do(req)
	if err != nil {
		return "", nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", nil, err
	}
	if resp.StatusCode != http.StatusOK {
		return "", nil, fmt.Errorf("npm %s: %s", pkg, resp.Status)
	}
	var doc struct {
		DistTags map[string]string         `json:"dist-tags"`
		Versions map[string]map[string]any `json:"versions"`
	}
	if err := json.Unmarshal(body, &doc); err != nil {
		return "", nil, fmt.Errorf("npm %s: %w", pkg, err)
	}
	all := make([]string, 0, len(doc.Versions))
	for v := range doc.Versions {
		all = append(all, v)
	}
	slices.Sort(all)
	return doc.DistTags["latest"], all, nil
}
