package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"
	"time"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/ax"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/gcp"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/snapshotgc"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/substrate"
)

// snapshot-gc is the operator's orphan-snapshot GC (Phase 6 plan D11), run
// as a one-off Job from the CronJob's template by `just exe-snapshot-gc`:
// in-cluster, so it reaches the Control API and ax-server the way L1 does.
// It prints what it would take and deletes nothing, unless -apply.
// internal/snapshotgc decides what it may take, and says why.

// envSnapshotsLocation is the location the ActorTemplates put snapshots
// under, gs://<bucket>/<root>/ (tofu/exe-cluster's ax_snapshots_location).
const envSnapshotsLocation = "EXE_SNAPSHOTS_LOCATION"

// gcTimeout bounds one run. Listing a bucket of this size and the store
// takes seconds; the deletes of a few prefixes, not much longer.
const gcTimeout = 10 * time.Minute

// What the GC reads and deletes, one interface per client, faked at these
// seams in its tests like the tick's.
type (
	snapshotStore interface {
		SnapshotRefs(ctx context.Context) (substrate.SnapshotRefs, error)
		ActorUID(ctx context.Context, atespace, name string) (string, error)
	}
	taskLister interface {
		Tasks(ctx context.Context) ([]ax.Task, error)
	}
	snapshotBucket interface {
		ListObjects(ctx context.Context, bucket, prefix string) ([]gcp.Object, error)
		DeleteObject(ctx context.Context, bucket, object string, generation int64) error
	}
)

type snapshotGC struct {
	store  snapshotStore
	tasks  taskLister
	bucket snapshotBucket
	// name and root are the snapshot location: gs://<name>/<root>.
	name string
	root string
	out  io.Writer
}

// allowList is the repeatable -allow flag.
type allowList []string

func (a *allowList) String() string { return strings.Join(*a, ",") }

func (a *allowList) Set(v string) error {
	*a = append(*a, v)
	return nil
}

func runSnapshotGC(args []string, stdout, stderr io.Writer) int {
	fs := flag.NewFlagSet("exe-reap snapshot-gc", flag.ContinueOnError)
	fs.SetOutput(stderr)
	apply := fs.Bool("apply", false, "delete the candidates; without it, print them and delete nothing")
	var allow allowList
	fs.Var(&allow, "allow", "take this prefix although a task in its atespace has lost its actor (repeatable)")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if fs.NArg() != 0 {
		fmt.Fprintf(stderr, "snapshot-gc takes flags only, got %q (-apply deletes)\n", fs.Args())
		return 2
	}
	name, root, err := snapshotgc.ParseLocation(os.Getenv(envSnapshotsLocation))
	if err != nil {
		fmt.Fprintf(stderr, "%s: %v\n", envSnapshotsLocation, err)
		return 2
	}

	sub, err := substrate.Dial(substrate.Options{
		Target:     envOr(envSubstrateTarget, defaultSubstrateTarget),
		ServerName: substrate.ServerName,
		TokenFile:  envOr(envSubstrateToken, defaultSubstrateToken),
		CAFile:     envOr(envSubstrateCA, defaultSubstrateCA),
	})
	if err != nil {
		fmt.Fprintf(stdout, "snapshot-gc: %v\n", err)
		return 1
	}
	defer func() { _ = sub.Close() }()
	axc, err := ax.Dial(envOr(envAXTarget, defaultAXTarget))
	if err != nil {
		fmt.Fprintf(stdout, "snapshot-gc: %v\n", err)
		return 1
	}
	defer func() { _ = axc.Close() }()

	g := &snapshotGC{store: sub, tasks: axc, bucket: gcp.New(), name: name, root: root, out: stdout}
	ctx, cancel := context.WithTimeout(context.Background(), gcTimeout)
	defer cancel()
	if err := g.run(ctx, time.Now(), *apply, allow); err != nil {
		fmt.Fprintf(stdout, "snapshot-gc: %v\n", err)
		return 1
	}
	return 0
}

// run reads, decides, reports, and with apply deletes. The bucket is listed
// before the store is read: a prefix written after the listing is never
// among the objects, and one written before it by an actor the store has is
// kept by the read that follows. The other order would leave a window where
// neither holds.
func (g *snapshotGC) run(ctx context.Context, now time.Time, apply bool, allow []string) error {
	o := snapshotgc.Observation{Now: now, Bucket: g.name, Root: g.root, Allow: allow}
	objects, err := g.bucket.ListObjects(ctx, g.name, g.root+"atespaces/")
	if err != nil {
		return err
	}
	for _, obj := range objects {
		o.Objects = append(o.Objects, snapshotgc.Object{Name: obj.Name, Updated: obj.Updated, Generation: obj.Generation})
	}
	refs, err := g.store.SnapshotRefs(ctx)
	if err != nil {
		return err
	}
	o.ActorUIDs, o.URIs = refs.ActorUIDs, refs.URIs
	if o.Tasks, err = g.taskActors(ctx); err != nil {
		return err
	}

	d := snapshotgc.Decide(o)
	g.report(o, d, apply)
	if d.Refusal != "" {
		return fmt.Errorf("refused, nothing deleted: %s", d.Refusal)
	}
	if !apply {
		return nil
	}
	for _, p := range d.Candidates {
		for _, obj := range p.Objects {
			if err := g.bucket.DeleteObject(ctx, g.name, obj.Name, obj.Generation); err != nil {
				return fmt.Errorf("deleting %s, and stopping there: %w", obj.Name, err)
			}
		}
		fmt.Fprintf(g.out, "deleted  %s  %d object(s)\n", p.Path, len(p.Objects))
	}
	fmt.Fprintf(g.out, "snapshot-gc: %d prefix(es) deleted\n", len(d.Candidates))
	return nil
}

// taskActors is every AX task with its actor's UID, looked up by name. A task
// whose actor the store does not have is Missing, which holds its atespace;
// a lookup that fails is a failed read.
func (g *snapshotGC) taskActors(ctx context.Context) ([]snapshotgc.Task, error) {
	tasks, err := g.tasks.Tasks(ctx)
	if err != nil {
		return nil, err
	}
	out := make([]snapshotgc.Task, 0, len(tasks))
	for _, t := range tasks {
		atespace, name, _ := strings.Cut(t.Key, "/")
		uid, err := g.store.ActorUID(ctx, atespace, name)
		switch {
		case errors.Is(err, substrate.ErrNoActor):
			out = append(out, snapshotgc.Task{Key: t.Key, Missing: true})
		case err != nil:
			return nil, err
		default:
			out = append(out, snapshotgc.Task{Key: t.Key, UID: uid})
		}
	}
	return out, nil
}

// report prints the decision for the operator, who reads the dry run before
// anyone runs -apply. It names paths inside the bucket, never the bucket.
func (g *snapshotGC) report(o snapshotgc.Observation, d snapshotgc.Decision, apply bool) {
	fmt.Fprintf(g.out, "snapshot-gc: %d object(s) under %satespaces/, %d actor(s) in the store, %d task(s)\n",
		len(o.Objects), o.Root, len(o.ActorUIDs), len(o.Tasks))
	for _, task := range d.MissingActors {
		fmt.Fprintf(g.out, "missing  task %s: the store has no actor for it\n", task)
	}
	for _, k := range d.Kept {
		fmt.Fprintf(g.out, "keep     %s  %s\n", k.Prefix.Path, k.Reason)
	}
	for _, p := range d.Candidates {
		fmt.Fprintf(g.out, "take     %s  %d object(s), newest %s\n", p.Path, len(p.Objects), p.Newest.UTC().Format(time.RFC3339))
	}
	switch {
	case d.Refusal != "":
		fmt.Fprintf(g.out, "snapshot-gc: REFUSED, nothing deleted: %s\n", d.Refusal)
	case !apply:
		fmt.Fprintf(g.out, "snapshot-gc: dry run, nothing deleted; %d prefix(es) to take, and -apply takes them\n", len(d.Candidates))
	}
}
