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
	"io"
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
	// recipes set for the operator's path. Named here so there is one list, and
	// spelled exactly as tofu/exe-platform/l2_enforcer.tf spells them:
	// tests/unit/test_exe_reaper_env_contract.py fails if the two drift, since a
	// drifted name is an enforcer that exits "missing required environment" on
	// every tick.
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
		// Its own exit path: every line it writes, the failure line included,
		// is the log contract on stdout.
		os.Exit(runEnforce(ctx, os.Args[2:], os.Stdout))
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

// runEnforce is `exe-reaper enforce`, the L2 Cloud Run job: one tick, reported
// through the log contract below, and an exit code for Cloud Run to record.
func runEnforce(ctx context.Context, args []string, out io.Writer) int {
	log := contractLog{out}
	fs := flag.NewFlagSet("enforce", flag.ExitOnError)
	dryRun := fs.Bool("dry-run", false, "decide and report, change nothing")
	if err := fs.Parse(args); err != nil {
		log.fail(err)
		return 1
	}
	cfg, err := loadConfig(envBucket, envSetSizeURI, envProject, envZone, envCluster, envNodePool)
	if err != nil {
		log.fail(err)
		return 1
	}
	e := enforcer{client: gcp.New(), cfg: cfg, log: log}
	return e.run(ctx, time.Now(), *dryRun)
}

// enforcer is L2's plumbing: what it reads and writes through, and where it
// reports. runEnforce builds it from the environment; the tests build it from
// httptest stand-ins for GCS and GKE, which is what lets a whole tick run, real
// HTTP client included, without a cloud.
type enforcer struct {
	client *gcp.Client
	cfg    config
	log    contractLog
}

// run is one tick as the job runs it. A tick that fails ends with the failure
// line of the log contract and exit code 1.
func (e enforcer) run(ctx context.Context, now time.Time, dryRun bool) int {
	if err := e.tick(ctx, now, dryRun); err != nil {
		e.log.fail(err)
		return 1
	}
	return 0
}

// tick is one L2 pass: read the three inputs, decide, act, record.
func (e enforcer) tick(ctx context.Context, now time.Time, dryRun bool) error {
	client, cfg := e.client, e.cfg

	// L2 is a job: it exits between ticks and has no memory. The consecutive
	// read-failure count therefore lives in enforce.json, the object L2 itself
	// owns -- which is why the three-failure rule is implementable at all.
	//
	// A record that cannot be read does not stop the tick from deciding: it is
	// L2's memory that is missing, not the lease, and an expired lease costs
	// the same either way. The tick decides as if this were the first one,
	// acts, and then fails instead of recording.
	prev, prevGeneration, recordErr := readEnforce(ctx, client, cfg.bucket)
	if recordErr != nil {
		e.log.warn(fmt.Sprintf("%v; deciding without the previous record", recordErr))
	}

	obs := lease.Observation{Now: now}
	obs.Lease, obs.LeaseOK = leaseFromRead(client.GetObject(ctx, cfg.bucket, leaseObject))

	if drainBody, _, derr := client.GetObject(ctx, cfg.bucket, drainObject); derr == nil {
		var d lease.Drain
		if json.Unmarshal(drainBody, &d) == nil {
			obs.Drain = d
		}
	}

	size, sizeErr := client.NodePoolSize(ctx, cfg.project, cfg.zone, cfg.cluster, cfg.nodePool)
	if sizeErr != nil {
		e.log.warn(fmt.Sprintf("node pool size unreadable, deciding as if a node may be up: %v", sizeErr))
	}
	obs.Nodes = nodesForDecision(size, sizeErr)

	// After the pool size, because the rule needs it: while the pool is at
	// zero the run resets, so a run carried across a stop cannot make the first
	// miss after the next wake a blind stop.
	obs.ConsecutiveReadFailures = lease.NextReadFailures(prev.ReadFailures, obs.LeaseOK, obs.Nodes)

	decision := lease.DecideL2(obs)
	key := pageKey(obs, prev)
	line := decisionReport{Decision: decision, Obs: obs, LeaseGeneration: key}

	if dryRun {
		// Changes nothing and records nothing, so it pages nothing either.
		line.DryRun = true
		e.log.decision(line)
		return nil
	}

	if decision.Action != lease.ActionWait {
		// Everything above took time, and the operator may have extended (or
		// slept, or woken) in the meantime. That write is a new lease
		// generation and the operator's latest word; this decision was about
		// the one before it. So the lease is read once more, right before the
		// stop, and a decision about a lease that has since moved is abandoned
		// for the next tick to make again (review finding #8).
		if moved, current := e.leaseMoved(ctx, obs); moved {
			e.log.warn(fmt.Sprintf("lease changed during this tick (%s); not stopping: the next tick decides on %s",
				describeLease(obs.Lease, obs.LeaseOK), describeLease(current, true)))
			return nil
		}
		if err := client.SetNodePoolSize(ctx, cfg.setSizeURI, 0); err != nil {
			// No decision line: a stop that was not made must not page as one.
			// The failure line carries what was decided.
			return fmt.Errorf("stopping the node pool (%s, %s): %w", decision.Action, decision.Reason, err)
		}
	}
	line.Notify = shouldPage(decision, key, prev)
	e.log.decision(line)

	if recordErr != nil {
		// No generation to write against, so a conditional write could only
		// lose to the record that is there. Fail the tick instead: the job
		// exits non-zero, and the failed-execution alert says so.
		return fmt.Errorf("not recording this tick: %w", recordErr)
	}

	record := enforceRecord{
		At:                 now,
		Action:             string(decision.Action),
		Reason:             string(decision.Reason),
		Notified:           line.Notify,
		ReadFailures:       obs.ConsecutiveReadFailures,
		LeaseGeneration:    key,
		NotifiedGeneration: prev.NotifiedGeneration,
	}
	if line.Notify {
		record.NotifiedGeneration = &key
	}
	body, err := json.Marshal(record)
	if err != nil {
		return err
	}
	// Conditional on the generation L2 itself last saw. Two enforcer executions
	// overlapping (a retry, a manual run) then produce one winner rather than a
	// silently interleaved record.
	err = client.PutObject(ctx, cfg.bucket, enforceObject, body, prevGeneration)
	switch {
	case errors.Is(err, gcp.ErrPreconditionFailed):
		e.log.warn(enforceObject + " changed during this tick; the other execution's record stands")
	case err != nil:
		return fmt.Errorf("writing the enforcement record: %w", err)
	}
	return nil
}

// leaseMoved reads lease.json again and reports whether it has moved since the
// observation: a new generation, or, for a decision taken blind, a lease that
// can be read at all. A read that fails is no evidence that anything moved.
func (e enforcer) leaseMoved(ctx context.Context, obs lease.Observation) (bool, lease.Lease) {
	current, ok := leaseFromRead(e.client.GetObject(ctx, e.cfg.bucket, leaseObject))
	if !ok {
		return false, lease.Lease{}
	}
	return !obs.LeaseOK || current.Generation != obs.Lease.Generation, current
}

func describeLease(l lease.Lease, readable bool) string {
	if !readable {
		return "no readable lease"
	}
	return fmt.Sprintf("generation %d", l.Generation)
}

// pageKey is the lease generation a forced stop is paged under: the lease this
// tick read, or, when it could read none, the last one an earlier tick did. A
// blind stop has no lease of its own to name, and keying it on the last one
// read is what keeps a run of blind stops to one page.
func pageKey(obs lease.Observation, prev enforceRecord) int64 {
	if obs.LeaseOK {
		return obs.Lease.Generation
	}
	return prev.LeaseGeneration
}

// shouldPage reports whether a decision pages the operator: a forced stop, and
// only the first under its lease generation (D4). The stop itself is repeated
// on every tick that sees the pool up -- setSize(0) is idempotent -- but a
// stuck stop, or a pool size that keeps reading as up, would otherwise page on
// every tick all night. A new lease is a new generation, so its forced stop
// pages again.
func shouldPage(d lease.Decision, key int64, prev enforceRecord) bool {
	if !d.Notify() {
		return false
	}
	return prev.NotifiedGeneration == nil || *prev.NotifiedGeneration != key
}

// --- the log contract ---------------------------------------------------------
//
// `exe-reaper enforce` writes one JSON object per line to stdout, and nothing
// else. Cloud Run lifts "severity" into the entry's level and "message" into
// its summary; the rest lands in jsonPayload, L2's fields under
// jsonPayload.exe_l2. The two L2 alerts in tofu/exe-platform/monitoring.tf read
// it, so these lines are an interface, not a diagnostic:
//
//	decision  event "decision", once per tick that decided. ERROR exactly when
//	          notify is set -- the first forced stop of a lease generation,
//	          which the forced-stop alert pages on. A repeat is WARNING.
//	failure   event "failure" at ERROR, the last line before exit 1. The
//	          failed-execution alert pages on ERROR that is not a decision.
//	warning   event "warning" at WARNING: something the tick worked around.
//	          Never ERROR, or a tick that did its job would page as failed.

const (
	severityInfo    = "INFO"
	severityNotice  = "NOTICE"
	severityWarning = "WARNING"
	severityError   = "ERROR"
)

type contractLog struct {
	w io.Writer
}

type logEntry struct {
	Severity string `json:"severity"`
	Message  string `json:"message"`
	L2       any    `json:"exe_l2"`
}

func (l contractLog) write(e logEntry) {
	body, err := json.Marshal(e)
	if err != nil {
		// Nothing above can fail to marshal; if it ever does, the line must
		// still arrive, at its severity.
		body = fmt.Appendf(nil, `{"severity":%q,"message":%q,"exe_l2":{"event":"failure"}}`,
			e.Severity, e.Message)
	}
	_, _ = l.w.Write(append(body, '\n'))
}

// decisionReport is what one tick decided, as the decision line reports it.
type decisionReport struct {
	Decision        lease.Decision
	Obs             lease.Observation
	LeaseGeneration int64
	Notify          bool
	DryRun          bool
}

type decisionFields struct {
	Event           string `json:"event"`
	Action          string `json:"action"`
	Reason          string `json:"reason"`
	Notify          bool   `json:"notify"`
	DryRun          bool   `json:"dryRun,omitempty"`
	Nodes           int    `json:"nodes"`
	ReadFailures    int    `json:"readFailures"`
	LeaseReadable   bool   `json:"leaseReadable"`
	LeaseGeneration int64  `json:"leaseGeneration"`
}

func (l contractLog) decision(d decisionReport) {
	severity := severityInfo
	switch {
	case d.Notify:
		severity = severityError
	case d.Decision.Action == lease.ActionStopForced || d.Decision.Reason == lease.ReasonTransientReadFailure:
		severity = severityWarning
	case d.Decision.Action == lease.ActionStopGraceful:
		severity = severityNotice
	}
	l.write(logEntry{
		Severity: severity,
		Message: fmt.Sprintf("L2 %s (%s): nodes %d, lease read failures %d",
			d.Decision.Action, d.Decision.Reason, d.Obs.Nodes, d.Obs.ConsecutiveReadFailures),
		L2: decisionFields{
			Event:           "decision",
			Action:          string(d.Decision.Action),
			Reason:          string(d.Decision.Reason),
			Notify:          d.Notify,
			DryRun:          d.DryRun,
			Nodes:           d.Obs.Nodes,
			ReadFailures:    d.Obs.ConsecutiveReadFailures,
			LeaseReadable:   d.Obs.LeaseOK,
			LeaseGeneration: d.LeaseGeneration,
		},
	})
}

type messageFields struct {
	Event string `json:"event"`
	Error string `json:"error,omitempty"`
}

func (l contractLog) warn(message string) {
	l.write(logEntry{Severity: severityWarning, Message: message, L2: messageFields{Event: "warning"}})
}

func (l contractLog) fail(err error) {
	l.write(logEntry{
		Severity: severityError,
		Message:  "exe-reaper enforce failed: " + err.Error(),
		L2:       messageFields{Event: "failure", Error: err.Error()},
	})
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

// enforceRecord is enforce.json: what L2 decided last, and the little it has
// to carry to the next tick.
type enforceRecord struct {
	At           time.Time `json:"at"`
	Action       string    `json:"action"`
	Reason       string    `json:"reason"`
	Notified     bool      `json:"notified"`
	ReadFailures int       `json:"readFailures"`
	// LeaseGeneration is the lease generation this tick read, or, when it read
	// none, the last one an earlier tick did (pageKey).
	LeaseGeneration int64 `json:"leaseGeneration,omitempty"`
	// NotifiedGeneration is the lease generation the last paged forced stop was
	// about; nil until the first page.
	NotifiedGeneration *int64 `json:"notifiedGeneration,omitempty"`
}

// readEnforce reads L2's own record, its only memory between ticks.
//
// Absent is the first tick: an empty record, and generation 0 so the write
// creates it. Unparsable is replaced: an empty record, with the generation it
// was read at so the write overwrites exactly that. Any other failure is an
// error, never an empty record: a record L2 cannot read is a read-failure run
// it cannot carry, and the conditional write that followed would lose to the
// object that is there -- on every tick, silently.
func readEnforce(ctx context.Context, client *gcp.Client, bucket string) (enforceRecord, int64, error) {
	body, generation, err := client.GetObject(ctx, bucket, enforceObject)
	switch {
	case errors.Is(err, gcp.ErrNotFound):
		return enforceRecord{}, 0, nil
	case err != nil:
		return enforceRecord{}, 0, fmt.Errorf("reading %s: %w", enforceObject, err)
	}
	var rec enforceRecord
	if json.Unmarshal(body, &rec) != nil {
		rec = enforceRecord{} // a partial decode is no record either
	}
	return rec, generation, nil
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

	switch rec, _, err := readEnforce(ctx, client, cfg.bucket); {
	case err != nil:
		fmt.Printf("last enforce   unreadable: %v\n", err)
	case rec.Action != "":
		fmt.Printf("last enforce   %s (%s) at %s\n", rec.Action, rec.Reason,
			rec.At.In(lease.Location()).Format(time.RFC3339))
	default:
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
