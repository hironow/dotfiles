package substrate

import (
	"context"
	"errors"
	"slices"
	"testing"

	"github.com/agent-substrate/substrate/pkg/proto/ateapipb"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// What the snapshot GC (plan D11) reads from the store: every actor's UID and
// every snapshot URI the store points at, and a task's actor looked up by name.

func (f *fakeControl) GetActor(ctx context.Context, req *ateapipb.GetActorRequest) (*ateapipb.Actor, error) {
	f.record(ctx, req.GetActor().GetAtespace())
	if f.getErr != nil {
		return nil, f.getErr
	}
	a, ok := f.named[req.GetActor().GetAtespace()+"/"+req.GetActor().GetName()]
	if !ok {
		return nil, status.Error(codes.NotFound, "actor not found")
	}
	return a, nil
}

func suspendedWith(atespace, name, uid, uri string) *ateapipb.Actor {
	a := actor(atespace, name, uid, ateapipb.ActorState_ACTOR_STATE_SUSPENDED, nil)
	a.Status.ExternalSnapshot = &ateapipb.ExternalSnapshot{SnapshotUri: uri}
	return a
}

func goldenAt(uri string) *ateapipb.ActorTemplate {
	return &ateapipb.ActorTemplate{Status: &ateapipb.ActorTemplateStatus{GoldenSnapshotStatus: &ateapipb.GoldenSnapshotStatus{
		GoldenSnapshot: &ateapipb.ExternalSnapshot{SnapshotUri: uri},
	}}}
}

func TestSnapshotRefsReadsEveryActorAndTemplateAndWhereEachPoints(t *testing.T) {
	// given actors and templates on several pages; one actor holds its own
	// snapshot, one golden actor none yet, one template a golden snapshot and
	// one a failed one
	f := newFakeControl()
	f.actorPages = [][]*ateapipb.Actor{
		{suspendedWith("exe", "p1", "u1", "gs://zz-snap/ax/atespaces/exe/actors/u1/snapshots/s1")},
		{},
		{actor("ate-golden", "g1", "u2", ateapipb.ActorState_ACTOR_STATE_RUNNING, nil)},
	}
	failed := &ateapipb.ActorTemplate{Status: &ateapipb.ActorTemplateStatus{GoldenSnapshotStatus: &ateapipb.GoldenSnapshotStatus{ErrorMessage: "boot failed"}}}
	f.templatePages = [][]*ateapipb.ActorTemplate{
		{failed},
		{goldenAt("gs://zz-snap/ax/atespaces/ate-golden/actors/u9/snapshots/g1")},
	}
	c := dial(t, serve(t, f, newTestCA(t, ServerName)))

	// when
	got, err := c.SnapshotRefs(context.Background())
	// then every actor's UID, golden ones included, and every URI the store
	// points at, whether an actor's or a template's
	if err != nil {
		t.Fatal(err)
	}
	if want := []string{"u1", "u2"}; !slices.Equal(got.ActorUIDs, want) {
		t.Errorf("actor UIDs %q, want %q", got.ActorUIDs, want)
	}
	wantURIs := []string{
		"gs://zz-snap/ax/atespaces/exe/actors/u1/snapshots/s1",
		"gs://zz-snap/ax/atespaces/ate-golden/actors/u9/snapshots/g1",
	}
	if !slices.Equal(got.URIs, wantURIs) {
		t.Errorf("URIs %q, want %q", got.URIs, wantURIs)
	}
	// and both lists were read across every atespace at once
	for _, a := range f.atespaces {
		if a != "" {
			t.Errorf("listed atespace %q; the GC must read every atespace, ate-golden included", a)
		}
	}
}

func TestSnapshotRefsIsAllOrNothing(t *testing.T) {
	// A GC that missed a page would take the prefixes of the actors on it.
	for name, setup := range map[string]func(f *fakeControl){
		"actors":    func(f *fakeControl) { f.actorPages = [][]*ateapipb.Actor{{}, {}}; f.failPage = 1 },
		"templates": func(f *fakeControl) { f.templatePages = [][]*ateapipb.ActorTemplate{{}, {}}; f.failPage = 1 },
	} {
		t.Run(name, func(t *testing.T) {
			f := newFakeControl()
			setup(f)
			c := dial(t, serve(t, f, newTestCA(t, ServerName)))
			if got, err := c.SnapshotRefs(context.Background()); err == nil {
				t.Errorf("read %+v when a page of %s failed; want an error", got, name)
			}
		})
	}
}

func TestActorUIDFindsATasksActorByName(t *testing.T) {
	// AX names a task's actor after the task, in the task's atespace, and
	// stores only that name: the UID, which names the snapshot prefix, has to
	// come from the store.
	f := newFakeControl()
	f.named = map[string]*ateapipb.Actor{"exe/p1": actor("exe", "p1", "u1", ateapipb.ActorState_ACTOR_STATE_SUSPENDED, nil)}
	c := dial(t, serve(t, f, newTestCA(t, ServerName)))

	uid, err := c.ActorUID(context.Background(), "exe", "p1")
	if err != nil {
		t.Fatal(err)
	}
	if uid != "u1" {
		t.Errorf("uid %q, want u1", uid)
	}
}

func TestActorUIDOfAnActorTheStoreDoesNotHaveIsErrNoActor(t *testing.T) {
	f := newFakeControl()
	c := dial(t, serve(t, f, newTestCA(t, ServerName)))

	if _, err := c.ActorUID(context.Background(), "exe", "gone"); !errors.Is(err, ErrNoActor) {
		t.Errorf("err %v, want ErrNoActor", err)
	}
}

func TestActorUIDThatFailsIsNotReadAsMissing(t *testing.T) {
	// "The store has no such actor" lets the operator take that atespace's
	// prefixes by name; "the store did not answer" must not.
	f := newFakeControl()
	f.getErr = status.Error(codes.Unavailable, "the store went away")
	c := dial(t, serve(t, f, newTestCA(t, ServerName)))

	_, err := c.ActorUID(context.Background(), "exe", "p1")
	if err == nil || errors.Is(err, ErrNoActor) {
		t.Errorf("err %v, want a failure that is not ErrNoActor", err)
	}
}
