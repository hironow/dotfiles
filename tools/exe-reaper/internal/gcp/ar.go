package gcp

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
)

// Artifact Registry, the little of it L1's retention step needs (Phase 6 plan
// D10): the packages of a repository, their tags, and creating or deleting one
// tag. A tag is what keeps a version out of the repository's cleanup policy
// (KEEP by the `inuse-` prefix), so these four calls are how L1 protects the
// image a live task will pull again at its next resume.
//
// Resource names are the API's own, with any slash in a package name escaped
// as %2F (ko's packages are nested, `substrate/ateapi`). They are passed
// through as they are: unescaping one would turn the package's slash into a
// path separator.

const artifactRegistryBase = "https://artifactregistry.googleapis.com/v1"

// arPageSize asks for pages as large as the API allows.
const arPageSize = 1000

func (c *Client) artifactRegistry() string {
	if c.ArtifactRegistryBase != "" {
		return c.ArtifactRegistryBase
	}
	return artifactRegistryBase
}

// ARTag is one tag of a package: its ID (`inuse-...`) and the digest of the
// version it points at.
type ARTag struct {
	ID     string
	Digest string
}

// ListPackages is every package in a repository
// (projects/P/locations/L/repositories/R), by resource name.
func (c *Client) ListPackages(ctx context.Context, repo string) ([]string, error) {
	var out []string
	err := c.arPages(ctx, repo+"/packages", func(raw json.RawMessage) error {
		var page struct {
			Packages []struct {
				Name string `json:"name"`
			} `json:"packages"`
		}
		if err := json.Unmarshal(raw, &page); err != nil {
			return err
		}
		for _, p := range page.Packages {
			out = append(out, p.Name)
		}
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("listing packages: %w", err)
	}
	return out, nil
}

// ListTags is every tag of a package, by resource name.
func (c *Client) ListTags(ctx context.Context, pkg string) ([]ARTag, error) {
	var out []ARTag
	err := c.arPages(ctx, pkg+"/tags", func(raw json.RawMessage) error {
		var page struct {
			Tags []struct {
				Name    string `json:"name"`
				Version string `json:"version"`
			} `json:"tags"`
		}
		if err := json.Unmarshal(raw, &page); err != nil {
			return err
		}
		for _, t := range page.Tags {
			_, id, _ := strings.Cut(t.Name, "/tags/")
			_, digest, _ := strings.Cut(t.Version, "/versions/")
			out = append(out, ARTag{ID: id, Digest: digest})
		}
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("listing tags: %w", err)
	}
	return out, nil
}

// CreateTag points tag id of a package at the version with that digest. A
// tag already there is the goal holding, not an error.
func (c *Client) CreateTag(ctx context.Context, pkg, id, digest string) error {
	body, err := json.Marshal(map[string]string{"version": pkg + "/versions/" + digest})
	if err != nil {
		return err
	}
	rawURL := c.artifactRegistry() + "/" + pkg + "/tags?tagId=" + url.QueryEscape(id)
	resp, err := c.do(ctx, http.MethodPost, rawURL, body, map[string]string{"Content-Type": "application/json"})
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()
	switch resp.StatusCode {
	case http.StatusOK, http.StatusConflict:
		return nil
	default:
		return fmt.Errorf("tagging %s %s: %w", pkg, id, statusError(resp))
	}
}

// DeleteTag removes tag id from a package. A tag already gone is the goal
// holding, not an error.
func (c *Client) DeleteTag(ctx context.Context, pkg, id string) error {
	rawURL := c.artifactRegistry() + "/" + pkg + "/tags/" + url.PathEscape(id)
	resp, err := c.do(ctx, http.MethodDelete, rawURL, nil, nil)
	if err != nil {
		return err
	}
	defer func() { _ = resp.Body.Close() }()
	switch resp.StatusCode {
	case http.StatusOK, http.StatusNotFound:
		return nil
	default:
		return fmt.Errorf("untagging %s %s: %w", pkg, id, statusError(resp))
	}
}

// arPages follows a list to its last page, handing each page's body to read.
func (c *Client) arPages(ctx context.Context, path string, read func(json.RawMessage) error) error {
	token := ""
	for {
		q := url.Values{"pageSize": {strconv.Itoa(arPageSize)}}
		if token != "" {
			q.Set("pageToken", token)
		}
		resp, err := c.do(ctx, http.MethodGet, c.artifactRegistry()+"/"+path+"?"+q.Encode(), nil, nil)
		if err != nil {
			return err
		}
		var raw json.RawMessage
		switch {
		case resp.StatusCode != http.StatusOK:
			err = statusError(resp)
		default:
			err = json.NewDecoder(resp.Body).Decode(&raw)
		}
		_ = resp.Body.Close()
		if err != nil {
			return err
		}
		if err := read(raw); err != nil {
			return err
		}
		var next struct {
			NextPageToken string `json:"nextPageToken"`
		}
		if err := json.Unmarshal(raw, &next); err != nil {
			return err
		}
		if next.NextPageToken == "" {
			return nil
		}
		token = next.NextPageToken
	}
}

// imageRef is an Artifact Registry Docker image pinned by digest:
// <location>-docker.pkg.dev/<project>/<repository>/<package...>[:tag]@sha256:<hex>.
var imageRef = regexp.MustCompile(`^([a-z0-9-]+)-docker\.pkg\.dev/([^/]+)/([^/]+)/([^:@]+)(?::[^@]*)?@(sha256:[0-9a-f]+)$`)

// ParseImageRef splits an image reference into its repository and package
// resource names and its digest. ok is false for anything that is not an
// Artifact Registry image pinned by digest: nothing a tag could protect.
func ParseImageRef(ref string) (repo, pkg, digest string, ok bool) {
	m := imageRef.FindStringSubmatch(ref)
	if m == nil {
		return "", "", "", false
	}
	repo = "projects/" + m[2] + "/locations/" + m[1] + "/repositories/" + m[3]
	return repo, repo + "/packages/" + url.PathEscape(m[4]), m[5], true
}
