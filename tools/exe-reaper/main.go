// Command exe-reaper owns the lease that decides whether an exe node may run.
//
// Five subcommands, three identities, one writer per object (section 3.2 of
// docs/plan/exe-google-ax.md):
//
//	wake / extend / sleep / status   operator's own credentials; writes lease.json
//	enforce                          the L2 Cloud Run job; writes enforce.json
//
// L1's `reap` lands in a later phase; its decision rules already live in
// internal/lease and are already tested, so that phase adds the in-cluster I/O,
// not new judgement.
//
// The rules are all in internal/lease and none of them are here. This file is
// plumbing: parse a flag, read two objects, call the decision function, act on
// what it says. That split is what lets the decision tables and the seeded
// simulation cover the dangerous part without a cluster.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"time"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/gcp"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/lease"
)

const (
	leaseObject   = "lease.json"
	drainObject   = "drain.json"
	enforceObject = "enforce.json"

	// Env vars the OpenTofu stack sets on the Cloud Run job, and the just
	// recipes set for the operator's path. Named here so there is one list.
	envBucket     = "EXE_OPS_BUCKET"
	envSetSizeURI = "EXE_NODE_POOL_SET_SIZE_URI"
	envProject    = "EXE_PROJECT_ID"
	envZone       = "EXE_ZONE"
	envCluster    = "EXE_CLUSTER_NAME"
	envNodePool   = "EXE_NODE_POOL"
)

type config struct {
	bucket     string
	setSizeURI string
	project    string
	zone       string
	cluster    string
	nodePool   string
}

func loadConfig(required ...string) (config, error) {
	c := config{
		bucket:     os.Getenv(envBucket),
		setSizeURI: os.Getenv(envSetSizeURI),
		project:    os.Getenv(envProject),
		zone:       os.Getenv(envZone),
		cluster:    os.Getenv(envCluster),
		nodePool:   os.Getenv(envNodePool),
	}
	byName := map[string]string{
		envBucket: c.bucket, envSetSizeURI: c.setSizeURI, envProject: c.project,
		envZone: c.zone, envCluster: c.cluster, envNodePool: c.nodePool,
	}
	var missing []string
	for _, name := range required {
		if byName[name] == "" {
			missing = append(missing, name)
		}
	}
	if len(missing) > 0 {
		return c, fmt.Errorf("missing required environment: %v", missing)
	}
	return c, nil
}

func main() {
	if len(os.Args) < 2 {
		usage()
		os.Exit(2)
	}
	ctx := context.Background()
	var err error
	switch os.Args[1] {
	case "wake":
		err = cmdLease(ctx, os.Args[2:], true)
	case "extend":
		err = cmdLease(ctx, os.Args[2:], false)
	case "sleep":
		err = cmdSleep(ctx, os.Args[2:])
	case "enforce":
		err = cmdEnforce(ctx, os.Args[2:])
	case "status":
		err = cmdStatus(ctx, os.Args[2:])
	case "-h", "--help", "help":
		usage()
		return
	default:
		fmt.Fprintf(os.Stderr, "unknown subcommand %q\n", os.Args[1])
		usage()
		os.Exit(2)
	}
	if err != nil {
		fmt.Fprintf(os.Stderr, "exe-reaper: %v\n", err)
		os.Exit(1)
	}
}

func usage() {
	fmt.Fprint(os.Stderr, `exe-reaper — the lease that bounds a running exe node

  wake [-for 2h]     authorise a node until a deadline, and start one
  extend [-for 2h]   push the deadline out; invalidates an earlier drained record
  sleep              set the deadline to now and let the drain run
  enforce            L2: one out-of-cluster enforcement tick
  status             what the lease says, without needing the cluster to be up

Every deadline is clamped so it cannot outlive the nightly cap, and a single
request may not exceed the maximum lease. Both limits are in
exe/lease-constants.json.
`)
}

// --- L0: wake / extend / sleep ----------------------------------------------

func cmdLease(ctx context.Context, args []string, startNode bool) error {
	name := "extend"
	if startNode {
		name = "wake"
	}
	fs := flag.NewFlagSet(name, flag.ExitOnError)
	forDur := fs.Duration("for", lease.DefaultLease, "how long to authorise the node for")
	if err := fs.Parse(args); err != nil {
		return err
	}

	required := []string{envBucket}
	if startNode {
		required = append(required, envSetSizeURI)
	}
	cfg, err := loadConfig(required...)
	if err != nil {
		return err
	}

	now := time.Now()
	deadline, clamped, err := lease.ClampDeadline(now, *forDur)
	if err != nil {
		return err
	}
	if clamped {
		fmt.Printf("clamped to the nightly cap: %s\n", deadline.In(lease.Location()).Format(time.RFC3339))
	}

	client := gcp.New()

	// Read for the generation, then write conditionally on it. Two operators
	// racing means one of them is told, rather than one silently losing.
	_, generation, err := client.GetObject(ctx, cfg.bucket, leaseObject)
	switch {
	case err == nil:
	case errors.Is(err, gcp.ErrNotFound):
		generation = 0 // create-only
	default:
		return fmt.Errorf("reading the lease: %w", err)
	}

	body, err := json.Marshal(lease.Lease{Deadline: deadline})
	if err != nil {
		return err
	}
	if err := client.PutObject(ctx, cfg.bucket, leaseObject, body, generation); err != nil {
		if errors.Is(err, gcp.ErrPreconditionFailed) {
			return errors.New("the lease changed while this command was running; re-run it")
		}
		return fmt.Errorf("writing the lease: %w", err)
	}
	fmt.Printf("lease until %s\n", deadline.In(lease.Location()).Format(time.RFC3339))

	if startNode {
		if err := client.SetNodePoolSize(ctx, cfg.setSizeURI, 1); err != nil {
			return fmt.Errorf("starting the node: %w", err)
		}
		fmt.Println("node pool set to 1")
	}
	return nil
}

func cmdSleep(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("sleep", flag.ExitOnError)
	if err := fs.Parse(args); err != nil {
		return err
	}
	cfg, err := loadConfig(envBucket)
	if err != nil {
		return err
	}
	client := gcp.New()

	_, generation, err := client.GetObject(ctx, cfg.bucket, leaseObject)
	if err != nil && !errors.Is(err, gcp.ErrNotFound) {
		return fmt.Errorf("reading the lease: %w", err)
	}
	if errors.Is(err, gcp.ErrNotFound) {
		generation = 0
	}

	// Expire the lease rather than shrinking the pool here. L1 then drains
	// gracefully and L2 stops the pool -- which keeps "one writer per object" and
	// keeps the ordering that saves the running actors.
	body, err := json.Marshal(lease.Lease{Deadline: time.Now()})
	if err != nil {
		return err
	}
	if err := client.PutObject(ctx, cfg.bucket, leaseObject, body, generation); err != nil {
		return fmt.Errorf("writing the lease: %w", err)
	}
	fmt.Println("lease expired; the drain will run and the pool will stop")
	return nil
}

// --- L2: enforce -------------------------------------------------------------

func cmdEnforce(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("enforce", flag.ExitOnError)
	dryRun := fs.Bool("dry-run", false, "decide and report, change nothing")
	if err := fs.Parse(args); err != nil {
		return err
	}
	cfg, err := loadConfig(envBucket, envSetSizeURI, envProject, envZone, envCluster, envNodePool)
	if err != nil {
		return err
	}
	client := gcp.New()
	now := time.Now()

	// L2 is a job: it exits between ticks and has no memory. The consecutive
	// read-failure count therefore lives in enforce.json, the object L2 itself
	// owns -- which is why the three-failure rule is implementable at all.
	prev, prevGeneration := readEnforce(ctx, client, cfg.bucket)

	obs := lease.Observation{Now: now}
	obs.Lease, obs.LeaseOK = leaseFromRead(client.GetObject(ctx, cfg.bucket, leaseObject))
	if obs.LeaseOK {
		obs.ConsecutiveReadFailures = 0
	} else {
		obs.ConsecutiveReadFailures = prev.ReadFailures + 1
	}

	if drainBody, _, derr := client.GetObject(ctx, cfg.bucket, drainObject); derr == nil {
		var d lease.Drain
		if json.Unmarshal(drainBody, &d) == nil {
			obs.Drain = d
		}
	}

	size, sizeErr := client.NodePoolSize(ctx, cfg.project, cfg.zone, cfg.cluster, cfg.nodePool)
	if sizeErr != nil {
		fmt.Fprintf(os.Stderr, "warning: node pool size unreadable, deciding as if a node may be up: %v\n", sizeErr)
	}
	obs.Nodes = nodesForDecision(size, sizeErr)

	decision := lease.DecideL2(obs)
	fmt.Printf("decision=%s reason=%s nodes=%d readFailures=%d\n",
		decision.Action, decision.Reason, obs.Nodes, obs.ConsecutiveReadFailures)

	if *dryRun {
		return nil
	}

	if decision.Action != lease.ActionWait {
		if err := client.SetNodePoolSize(ctx, cfg.setSizeURI, 0); err != nil {
			return fmt.Errorf("stopping the node pool: %w", err)
		}
	}

	record := enforceRecord{
		At:           now,
		Action:       string(decision.Action),
		Reason:       string(decision.Reason),
		Notified:     decision.Notify(),
		ReadFailures: obs.ConsecutiveReadFailures,
	}
	body, err := json.Marshal(record)
	if err != nil {
		return err
	}
	// Conditional on the generation L2 itself last saw. Two enforcer executions
	// overlapping (a retry, a manual run) then produce one winner rather than a
	// silently interleaved record.
	if err := client.PutObject(ctx, cfg.bucket, enforceObject, body, prevGeneration); err != nil &&
		!errors.Is(err, gcp.ErrPreconditionFailed) {
		return fmt.Errorf("writing the enforcement record: %w", err)
	}
	return nil
}

// nodesForDecision is the pool size L2 decides on. An unreadable size counts as
// one node, not zero: zero is DecideL2's "already stopped, nothing to do", so
// reading an error as zero would switch the money stop off exactly when its view
// of the pool is broken. One costs at most a redundant setSize(0), which is a
// harmless 200 on a pool already at zero (L3 does it every night).
func nodesForDecision(size int, err error) int {
	if err != nil {
		return 1
	}
	return size
}

// leaseFromRead is L2's view of one read of lease.json: the lease, and whether
// it was readable at all.
//
// The generation comes from the SAME read as the body. It is what a drain
// record is checked against, and a second read for it could return a newer
// generation than the body it is paired with -- an extend landing in between
// would then make an old `drained` look current.
//
// A deleted lease is a read failure, not an expired lease, exactly as the Quint
// model's leaseReadBreaks has it ("the object was deleted, the bucket is
// 503-ing"). The difference is who stops the pool: read as expired-long-ago, a
// deleted lease is forced on the very next tick, over the top of an L1 drain that
// is saving the actors; read as a failure, L1 gets its two ticks, and L2 forces on
// the third.
func leaseFromRead(body []byte, generation int64, err error) (lease.Lease, bool) {
	if err != nil {
		return lease.Lease{}, false
	}
	var l lease.Lease
	if json.Unmarshal(body, &l) != nil {
		return lease.Lease{}, false
	}
	l.Generation = generation
	return l, true
}

type enforceRecord struct {
	At           time.Time `json:"at"`
	Action       string    `json:"action"`
	Reason       string    `json:"reason"`
	Notified     bool      `json:"notified"`
	ReadFailures int       `json:"readFailures"`
}

func readEnforce(ctx context.Context, client *gcp.Client, bucket string) (enforceRecord, int64) {
	body, generation, err := client.GetObject(ctx, bucket, enforceObject)
	if err != nil {
		return enforceRecord{}, 0
	}
	var rec enforceRecord
	if json.Unmarshal(body, &rec) != nil {
		return enforceRecord{}, generation
	}
	return rec, generation
}

// --- status ------------------------------------------------------------------

func cmdStatus(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("status", flag.ExitOnError)
	if err := fs.Parse(args); err != nil {
		return err
	}
	cfg, err := loadConfig(envBucket, envProject, envZone, envCluster, envNodePool)
	if err != nil {
		return err
	}
	client := gcp.New()
	now := time.Now()

	// Everything here comes from GCP APIs, never from the cluster. The whole
	// point is that status answers while the cluster is asleep: a status command
	// that needs kubectl hangs for a minute and then fails, exactly when the
	// operator is trying to find out why nothing is running.
	fmt.Printf("now            %s\n", now.In(lease.Location()).Format(time.RFC3339))

	switch body, generation, err := client.GetObject(ctx, cfg.bucket, leaseObject); {
	case errors.Is(err, gcp.ErrNotFound):
		fmt.Println("lease          (none) — nothing is authorised")
	case err != nil:
		fmt.Printf("lease          unreadable: %v\n", err)
	default:
		var l lease.Lease
		if json.Unmarshal(body, &l) != nil {
			fmt.Println("lease          unparsable")
			break
		}
		remaining := l.Deadline.Sub(now).Round(time.Minute)
		state := "expired"
		if remaining > 0 {
			state = "live, " + remaining.String() + " remaining"
		}
		fmt.Printf("lease          until %s (%s, generation %d)\n",
			l.Deadline.In(lease.Location()).Format(time.RFC3339), state, generation)
	}

	if body, _, err := client.GetObject(ctx, cfg.bucket, drainObject); err == nil {
		var d lease.Drain
		if json.Unmarshal(body, &d) == nil {
			fmt.Printf("drain          %s (heartbeat %s, lease generation %d)\n",
				orNone(string(d.Phase)), d.Heartbeat.In(lease.Location()).Format(time.RFC3339), d.LeaseGeneration)
		}
	} else {
		fmt.Println("drain          (none)")
	}

	if rec, _ := readEnforce(ctx, client, cfg.bucket); rec.Action != "" {
		fmt.Printf("last enforce   %s (%s) at %s\n", rec.Action, rec.Reason,
			rec.At.In(lease.Location()).Format(time.RFC3339))
	} else {
		fmt.Println("last enforce   (none)")
	}

	if size, err := client.NodePoolSize(ctx, cfg.project, cfg.zone, cfg.cluster, cfg.nodePool); err == nil {
		fmt.Printf("node pool      %d node(s)\n", size)
		if size == 0 {
			fmt.Println("tasks          (asleep — task counts need the cluster up)")
		}
	} else {
		fmt.Printf("node pool      unreadable: %v\n", err)
	}

	fmt.Printf("nightly cap    %02d:00 %s, daily stop %02d:00\n",
		lease.NightlyCapHour, lease.TimezoneName, lease.L3StopHour)
	return nil
}

func orNone(s string) string {
	if s == "" {
		return "(none)"
	}
	return s
}
