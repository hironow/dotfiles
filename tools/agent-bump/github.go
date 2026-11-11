package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"strings"
	"time"

	json "github.com/goccy/go-json/v2"

	"github.com/hironow/dotfiles/tools/agent-bump/internal/bump"
)

// gitHub is the Releases adapter for api.github.com.
type gitHub struct {
	client *http.Client
	base   string
	token  string
}

// newGitHub uses GITHUB_TOKEN, else `gh auth token`. Without a token the
// API allows 60 requests an hour, which the table alone can use up.
func newGitHub(ctx context.Context) (*gitHub, error) {
	token := strings.TrimSpace(os.Getenv("GITHUB_TOKEN"))
	if token == "" {
		out, err := exec.CommandContext(ctx, "gh", "auth", "token").Output()
		if err == nil {
			token = strings.TrimSpace(string(out))
		}
	}
	if token == "" {
		return nil, errors.New("no GitHub token: set GITHUB_TOKEN or run `gh auth login`")
	}
	return &gitHub{client: &http.Client{Timeout: 30 * time.Second}, base: "https://api.github.com", token: token}, nil
}

func (g *gitHub) get(ctx context.Context, path, accept string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, g.base+path, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Accept", accept)
	req.Header.Set("Authorization", "Bearer "+g.token)
	req.Header.Set("X-GitHub-Api-Version", "2022-11-28")
	resp, err := g.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("GET %s: %s", path, resp.Status)
	}
	return body, nil
}

func escapePath(p string) string {
	parts := strings.Split(p, "/")
	for i, part := range parts {
		parts[i] = url.PathEscape(part)
	}
	return strings.Join(parts, "/")
}

func (g *gitHub) Latest(ctx context.Context, repo string) (string, error) {
	body, err := g.get(ctx, "/repos/"+repo+"/releases/latest", "application/vnd.github+json")
	if err != nil {
		return "", err
	}
	var r struct {
		TagName string `json:"tag_name"`
	}
	if err := json.Unmarshal(body, &r); err != nil {
		return "", err
	}
	return r.TagName, nil
}

func (g *gitHub) Commit(ctx context.Context, repo, ref string) (string, error) {
	body, err := g.get(ctx, "/repos/"+repo+"/commits/"+url.PathEscape(ref), "application/vnd.github.sha")
	return strings.TrimSpace(string(body)), err
}

func (g *gitHub) Tree(ctx context.Context, repo, ref string) ([]bump.TreeEntry, error) {
	body, err := g.get(ctx, "/repos/"+repo+"/git/trees/"+url.PathEscape(ref)+"?recursive=1", "application/vnd.github+json")
	if err != nil {
		return nil, err
	}
	var r struct {
		Tree []struct {
			Path string `json:"path"`
			Type string `json:"type"`
			SHA  string `json:"sha"`
		} `json:"tree"`
		Truncated bool `json:"truncated"`
	}
	if err := json.Unmarshal(body, &r); err != nil {
		return nil, err
	}
	if r.Truncated {
		return nil, fmt.Errorf("%s@%s: the tree is too large for one request", repo, ref)
	}
	out := make([]bump.TreeEntry, 0, len(r.Tree))
	for _, e := range r.Tree {
		out = append(out, bump.TreeEntry{Path: e.Path, Dir: e.Type == "tree", SHA: e.SHA})
	}
	return out, nil
}

func (g *gitHub) File(ctx context.Context, repo, ref, path string) ([]byte, error) {
	return g.get(ctx, "/repos/"+repo+"/contents/"+escapePath(path)+"?ref="+url.QueryEscape(ref), "application/vnd.github.raw+json")
}
