package ax

import (
	"context"
	"errors"
	"fmt"
	"net"
	"slices"
	"strings"
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
	images    map[string]string
	order     []string // ListTasks order, newest first like the Redis index
	fail      error
	suspended []string
	deleted   []string
	listCalls []int64 // the offsets asked for
}

func (f *fakeAX) ListTasks(_ context.Context, req *v1alpha1.ListTasksRequest) (*v1alpha1.ListTasksResponse, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.fail != nil {
		return nil, f.fail
	}
	if req.GetAtespace() != "" {
		return nil, status.Error(codes.InvalidArgument, "the reaper lists every atespace at once")
	}
	f.listCalls = append(f.listCalls, req.GetOffset())
	limit := req.GetLimit()
	if limit <= 0 {
		limit = 50
	}
	var out []*v1alpha1.Task
	for i := req.GetOffset(); i < int64(len(f.order)) && i < req.GetOffset()+limit; i++ {
		atespace, name, _ := strings.Cut(f.order[i], "/")
		out = append(out, &v1alpha1.Task{
			Metadata: &v1alpha1.ObjectMeta{Atespace: atespace, Name: name},
			Spec:     &v1alpha1.TaskSpec{Image: f.images[f.order[i]], Suspend: f.tasks[f.order[i]]},
		})
	}
	return &v1alpha1.ListTasksResponse{Tasks: out}, nil
}

func (f *fakeAX) DeleteTask(_ context.Context, req *v1alpha1.DeleteTaskRequest) (*v1alpha1.DeleteTaskResponse, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.fail != nil {
		return nil, f.fail
	}
	key := req.GetAtespace() + "/" + req.GetName()
	if _, ok := f.tasks[key]; !ok {
		return nil, status.Errorf(codes.NotFound, "task %q not found in atespace %q", req.GetName(), req.GetAtespace())
	}
	delete(f.tasks, key)
	f.deleted = append(f.deleted, key)
	return &v1alpha1.DeleteTaskResponse{}, nil
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

func TestTasksReadsEveryPageOfEveryAtespace(t *testing.T) {
	// ListTasks pages by offset, 50 by default; a short page is the last.
	f := &fakeAX{tasks: map[string]bool{}, images: map[string]string{}}
	for i := range 2*taskPage + 1 {
		key := fmt.Sprintf("exe/t%03d", i)
		f.tasks[key] = i%2 == 0
		f.images[key] = "img-" + key
		f.order = append(f.order, key)
	}
	f.order = append(f.order, "other/x")
	f.tasks["other/x"] = false
	c := serve(t, f)

	got, err := c.Tasks(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 2*taskPage+2 {
		t.Fatalf("read %d tasks, want %d", len(got), 2*taskPage+2)
	}
	if got[0].Key != "exe/t000" || got[0].Image != "img-exe/t000" || got[len(got)-1].Key != "other/x" {
		t.Errorf("first %+v, last %+v", got[0], got[len(got)-1])
	}
	if !slices.Equal(f.listCalls, []int64{0, taskPage, 2 * taskPage}) {
		t.Errorf("asked for offsets %v", f.listCalls)
	}
}

func TestATaskListThatFailsIsAFailedRead(t *testing.T) {
	c := serve(t, &fakeAX{fail: status.Error(codes.Unavailable, "redis is down")})
	if got, err := c.Tasks(context.Background()); err == nil {
		t.Errorf("read %v from a failing server", got)
	}
}

func TestDeleteAsksAXToDeleteTheTask(t *testing.T) {
	f := &fakeAX{tasks: map[string]bool{"exe/p1": true}}
	c := serve(t, f)

	if err := c.Delete(context.Background(), "exe/p1"); err != nil {
		t.Fatal(err)
	}
	if !slices.Equal(f.deleted, []string{"exe/p1"}) {
		t.Errorf("deleted %v", f.deleted)
	}
	// already gone is the goal holding
	if err := c.Delete(context.Background(), "exe/p1"); !errors.Is(err, ErrNoTask) {
		t.Errorf("deleting a task AX no longer has: %v, want ErrNoTask", err)
	}
	if err := c.Delete(context.Background(), "p1"); err == nil {
		t.Error("a key without an atespace was sent")
	}
}
