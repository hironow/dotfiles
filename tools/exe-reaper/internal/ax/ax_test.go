package ax

import (
	"context"
	"errors"
	"net"
	"slices"
	"sync"
	"testing"

	"github.com/google/ax/pkg/apis/v1alpha1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// fakeAX is ax-server as L1 uses it: SuspendTask, over the plaintext HTTP/2
// ax-server itself listens on (cmd/ax-server: SetUnencryptedHTTP2). A real gRPC
// server on a real listener, so the client's dial options run for real.
type fakeAX struct {
	v1alpha1.UnimplementedAXServer

	mu        sync.Mutex
	tasks     map[string]bool // "<atespace>/<name>" -> spec.suspend
	fail      error
	suspended []string
}

func (f *fakeAX) SuspendTask(_ context.Context, req *v1alpha1.SuspendTaskRequest) (*v1alpha1.Task, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.fail != nil {
		return nil, f.fail
	}
	key := req.GetAtespace() + "/" + req.GetName()
	if _, ok := f.tasks[key]; !ok {
		return nil, status.Errorf(codes.NotFound, "task %q not found in atespace %q", req.GetName(), req.GetAtespace())
	}
	f.tasks[key] = true
	f.suspended = append(f.suspended, key)
	return &v1alpha1.Task{Spec: &v1alpha1.TaskSpec{Suspend: true}}, nil
}

func serve(t *testing.T, f *fakeAX) *Client {
	t.Helper()
	lis, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	srv := grpc.NewServer()
	v1alpha1.RegisterAXServer(srv, f)
	go func() { _ = srv.Serve(lis) }()
	t.Cleanup(srv.Stop)

	c, err := Dial(lis.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = c.Close() })
	return c
}

func TestSuspendAsksAXToSuspendTheTask(t *testing.T) {
	f := &fakeAX{tasks: map[string]bool{"exe/p1": false, "exe/p2": false}}
	c := serve(t, f)

	if err := c.Suspend(context.Background(), "exe/p1"); err != nil {
		t.Fatal(err)
	}
	if !slices.Equal(f.suspended, []string{"exe/p1"}) || f.tasks["exe/p2"] {
		t.Errorf("suspended %v, tasks %v: want exactly exe/p1", f.suspended, f.tasks)
	}
}

func TestSuspendingATaskAXDoesNotHaveIsErrNoTask(t *testing.T) {
	// An actor with no task behind it (deleted meanwhile, or never AX's) cannot
	// be suspended through AX. The tick reports it and carries on; the drain
	// then waits, and the ceiling is what ends it.
	c := serve(t, &fakeAX{tasks: map[string]bool{}})

	if err := c.Suspend(context.Background(), "exe/gone"); !errors.Is(err, ErrNoTask) {
		t.Errorf("err = %v, want ErrNoTask", err)
	}
}

func TestAnyOtherFailureIsNotErrNoTask(t *testing.T) {
	c := serve(t, &fakeAX{fail: status.Error(codes.Unavailable, "redis is down")})

	err := c.Suspend(context.Background(), "exe/p1")
	if err == nil || errors.Is(err, ErrNoTask) {
		t.Errorf("err = %v, want a plain failure", err)
	}
}

func TestATaskKeyWithoutAnAtespaceIsRefused(t *testing.T) {
	// "<atespace>/<name>" is how L1 names a task (substrate.Actors). AX would
	// read a bare name as atespace "default", and suspend a different task.
	c := serve(t, &fakeAX{tasks: map[string]bool{"default/p1": false}})

	for _, key := range []string{"p1", "/p1", "exe/", ""} {
		if err := c.Suspend(context.Background(), key); err == nil {
			t.Errorf("Suspend(%q) went through", key)
		}
	}
}
