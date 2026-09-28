// Package ax is L1's use of ax-server: suspending a task during a drain, and,
// for retention, listing every task and deleting one whose TTL ran out.
//
// L1 suspends and deletes through AX, never through Substrate directly, because the
// ax-controller owns each task's lifecycle: an actor suspended behind its back
// is one AX still records as running, and resumes. ax-server's SuspendTask
// only records spec.suspend=true; the controller carries it out, which is why
// the drain keeps the controller up until nothing is awake (plan D2).
//
// ax-server listens for plaintext HTTP/2 (cmd/ax-server) behind a deny-all
// NetworkPolicy with one allow rule for the reaper, so the connection carries
// no credentials: the policy is the access control (plan F10). The stubs are
// the pinned release's (github.com/google/ax, held to exe/versions.json by
// scripts/check_exe_pins.py).
package ax

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"github.com/google/ax/pkg/apis/v1alpha1"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/status"
)

// ErrNoTask is a suspend for a task AX does not have.
var ErrNoTask = errors.New("AX has no such task")

// Client is a connection to ax-server.
type Client struct {
	conn *grpc.ClientConn
	ax   v1alpha1.AXClient
}

// Dial prepares a client for ax-server at target (host:port). Like
// grpc.NewClient it does not connect; the first call does.
func Dial(target string) (*Client, error) {
	conn, err := grpc.NewClient(target, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		return nil, fmt.Errorf("preparing a client for ax-server at %s: %w", target, err)
	}
	return &Client{conn: conn, ax: v1alpha1.NewAXClient(conn)}, nil
}

// Close releases the connection.
func (c *Client) Close() error { return c.conn.Close() }

// Suspend asks AX to suspend the task named "<atespace>/<name>", the form
// substrate.Actors gives each task. AX reads a missing atespace as "default",
// so a key without both halves is refused rather than sent.
func (c *Client) Suspend(ctx context.Context, task string) error {
	atespace, name, ok := strings.Cut(task, "/")
	if !ok || atespace == "" || name == "" {
		return fmt.Errorf("task %q is not <atespace>/<name>", task)
	}
	_, err := c.ax.SuspendTask(ctx, &v1alpha1.SuspendTaskRequest{Atespace: atespace, Name: name})
	switch {
	case err == nil:
		return nil
	case status.Code(err) == codes.NotFound:
		return fmt.Errorf("suspending %s: %w", task, ErrNoTask)
	default:
		return fmt.Errorf("suspending %s: %w", task, err)
	}
}

// taskPage is how many tasks one ListTasks call asks for. ax-server pages by
// offset over its newest-first index, so a short page is the last.
const taskPage = 200

// maxTaskPages bounds one listing: far beyond any number of tasks this
// cluster holds.
const maxTaskPages = 1000

// Task is one AX task, as retention needs it.
type Task struct {
	// Key is "<atespace>/<name>", the form substrate.Actors gives a task.
	Key string
	// Image is spec.image as AX stores it: the reference the task runs.
	Image string
}

// Tasks is every task in every atespace. Offsets can shift under a
// concurrent create or delete, which may repeat or miss a task for one tick;
// retention tolerates both (a missed image starts no clock it cannot restart,
// and a missed TTL fires on the next tick).
func (c *Client) Tasks(ctx context.Context) ([]Task, error) {
	var out []Task
	seen := map[string]bool{}
	for page := range maxTaskPages {
		resp, err := c.ax.ListTasks(ctx, &v1alpha1.ListTasksRequest{Limit: taskPage, Offset: int64(page) * taskPage})
		if err != nil {
			return nil, fmt.Errorf("listing tasks: %w", err)
		}
		for _, t := range resp.GetTasks() {
			key := t.GetMetadata().GetAtespace() + "/" + t.GetMetadata().GetName()
			if seen[key] {
				continue
			}
			seen[key] = true
			out = append(out, Task{Key: key, Image: t.GetSpec().GetImage()})
		}
		if len(resp.GetTasks()) < taskPage {
			return out, nil
		}
	}
	return nil, fmt.Errorf("listing tasks: still paging after %d pages", maxTaskPages)
}

// Delete asks AX to delete the task named "<atespace>/<name>". AX marks it
// Terminating and its controller tears the actor down. A task AX does not
// have is ErrNoTask.
func (c *Client) Delete(ctx context.Context, task string) error {
	atespace, name, ok := strings.Cut(task, "/")
	if !ok || atespace == "" || name == "" {
		return fmt.Errorf("task %q is not <atespace>/<name>", task)
	}
	_, err := c.ax.DeleteTask(ctx, &v1alpha1.DeleteTaskRequest{Atespace: atespace, Name: name})
	switch {
	case err == nil:
		return nil
	case status.Code(err) == codes.NotFound:
		return fmt.Errorf("deleting %s: %w", task, ErrNoTask)
	default:
		return fmt.Errorf("deleting %s: %w", task, err)
	}
}
