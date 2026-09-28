package substrate

import (
	"context"
	"errors"
	"fmt"

	"github.com/agent-substrate/substrate/pkg/proto/ateapipb"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// What the orphan-snapshot GC (Phase 6 plan D11) reads from the store. Like
// the drain's reads, each is all or nothing: a GC that missed a page would
// take the prefixes of the actors on it.

// ErrNoActor is an actor the store does not have, distinctly from a store
// that did not answer.
var ErrNoActor = errors.New("the store has no such actor")

// SnapshotRefs is everything in the store that can hold a snapshot prefix.
type SnapshotRefs struct {
	// ActorUIDs is every actor's UID, in every atespace, ate-golden
	// included. An actor's own snapshots live under its UID.
	ActorUIDs []string
	// URIs is every snapshot URI the store points at: each actor's external
	// snapshot, and each ActorTemplate's golden snapshot, which lives under
	// the golden actor that took it and outlives that actor.
	URIs []string
}

// SnapshotRefs reads every actor and every ActorTemplate, across all
// atespaces, to the last page.
func (c *Client) SnapshotRefs(ctx context.Context) (SnapshotRefs, error) {
	var refs SnapshotRefs
	err := scan(ctx, func(ctx context.Context, token string) (string, error) {
		resp, err := c.control.ListActors(ctx, &ateapipb.ListActorsRequest{PageSize: pageSize, PageToken: token})
		if err != nil {
			return "", err
		}
		for _, a := range resp.GetActors() {
			refs.ActorUIDs = append(refs.ActorUIDs, a.GetMetadata().GetUid())
			if uri := a.GetStatus().GetExternalSnapshot().GetSnapshotUri(); uri != "" {
				refs.URIs = append(refs.URIs, uri)
			}
		}
		return resp.GetNextPageToken(), nil
	})
	if err != nil {
		return SnapshotRefs{}, fmt.Errorf("listing actors: %w", err)
	}
	err = scan(ctx, func(ctx context.Context, token string) (string, error) {
		resp, err := c.control.ListActorTemplates(ctx, &ateapipb.ListActorTemplatesRequest{PageSize: pageSize, PageToken: token})
		if err != nil {
			return "", err
		}
		for _, t := range resp.GetActorTemplates() {
			if uri := t.GetStatus().GetGoldenSnapshotStatus().GetGoldenSnapshot().GetSnapshotUri(); uri != "" {
				refs.URIs = append(refs.URIs, uri)
			}
		}
		return resp.GetNextPageToken(), nil
	})
	if err != nil {
		return SnapshotRefs{}, fmt.Errorf("listing actor templates: %w", err)
	}
	return refs, nil
}

// ActorUID is the UID of the actor named name in atespace. AX names a task's
// actor after the task and stores only that name, so this is how a task's
// snapshot prefix is found. An actor the store does not have is ErrNoActor.
func (c *Client) ActorUID(ctx context.Context, atespace, name string) (string, error) {
	a, err := c.control.GetActor(ctx, &ateapipb.GetActorRequest{Actor: &ateapipb.ObjectRef{Atespace: atespace, Name: name}})
	switch {
	case status.Code(err) == codes.NotFound:
		return "", fmt.Errorf("actor %s/%s: %w", atespace, name, ErrNoActor)
	case err != nil:
		return "", fmt.Errorf("getting actor %s/%s: %w", atespace, name, err)
	}
	uid := a.GetMetadata().GetUid()
	if uid == "" {
		return "", fmt.Errorf("actor %s/%s came back without a UID", atespace, name)
	}
	return uid, nil
}
