// Command exe-reaper owns the lease that decides whether an exe node may run.
//
// Seven subcommands, two identities, one writer per object (section 3.2 of
// docs/plan/exe-google-ax.md):
//
//	wake / extend / sleep            operator's own credentials; writes lease.json
//	keep                             operator's own credentials; writes keep.json
//	status / may-start               operator's own credentials; reads only
//	enforce                          the L2 Cloud Run job; writes enforce.json
//
// L1, the in-cluster drain, is a second binary in this module, cmd/exe-reap.
// It links the gRPC stubs for AX and Substrate; this one links the standard
// library and this module only (deps_test.go), because it is the one that
// shrinks the pool.
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
	"slices"
	"strings"
	"time"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/gcp"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/lease"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/ops"
)

const (
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

// errPositionalArgs is a command given an argument it does not take. Every
// value goes through a flag, and anything else is refused rather than
// ignored: `wake 5m` once meant a default-length lease.
var errPositionalArgs = errors.New("unexpected argument")

// noArgs refuses whatever the flags did not consume.
func noArgs(fs *flag.FlagSet) error {
	if fs.NArg() > 0 {
		return fmt.Errorf("%w %q: %s takes flags only", errPositionalArgs, fs.Arg(0), fs.Name())
	}
	return nil
}

// commandTimeout bounds every command, end to end. Each request has its own
// timeout, but a command makes several, and the L2 job's task limit is 120 s
// (tofu/exe-platform/l2_enforcer.tf): a tick stopped by this deadline still
// writes its failure line, where one killed at the limit leaves only Cloud
// Run's record that it failed. tests/unit/test_exe_reaper_env_contract.py
// keeps the two apart.
const commandTimeout = 90 * time.Second

// commandContext is the context every command runs under.
func commandContext(parent context.Context) (context.Context, context.CancelFunc) {
	return context.WithTimeout(parent, commandTimeout)
}

func main() {
	ctx, cancel := commandContext(context.Background())
	code := run(ctx, os.Args[1:])
	cancel()
	os.Exit(code)
}

// run dispatches one command and returns the process's exit code.
func run(ctx context.Context, args []string) int {
	if len(args) < 1 {
		usage()
		return 2
	}
	var err error
	switch args[0] {
	case "wake":
		err = cmdLease(ctx, args[1:], true)
	case "extend":
		err = cmdLease(ctx, args[1:], false)
	case "sleep":
		err = cmdSleep(ctx, args[1:])
	case "enforce":
		// Its own exit path: every line it writes, the failure line included,
		// is the log contract on stdout.
		return runEnforce(ctx, args[1:], os.Stdout)
	case "status":
		err = cmdStatus(ctx, args[1:])
	case "may-start":
		err = cmdMayStart(ctx, args[1:])
	case "keep":
		err = cmdKeep(ctx, args[1:])
	case "-h", "--help", "help":
		usage()
		return 0
	default:
		fmt.Fprintf(os.Stderr, "unknown subcommand %q\n", args[0])
		usage()
		return 2
	}
	if errors.Is(err, errRefused) {
		fmt.Fprintf(os.Stderr, "exe-reaper: %v\n", err)
		return 3
	}
	if err != nil {
		fmt.Fprintf(os.Stderr, "exe-reaper: %v\n", err)
		return 1
	}
	return 0
}

func usage() {
	fmt.Fprint(os.Stderr, `exe-reaper — the lease that bounds a running exe node

  wake [-for 2h]     authorise a node until a deadline, and start one
  extend [-for 2h]   push the deadline out; invalidates an earlier drained record
  sleep              set the deadline to now and let the drain run
  enforce            L2: one out-of-cluster enforcement tick
  status             what the lease says, without needing the cluster to be up
  may-start [-need 10m]
                     exit 0 if a new task may start now and the lease has that
                     long left; exit 3 with the reason if not (ax-job, ax-exec)
  keep add|rm TASK   exempt a task from the 30-day TTL, or stop exempting it
  keep ls            the exempted tasks

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
	if fs.NArg() > 0 {
		return fmt.Errorf("%w %q: ask for a duration with -for %s", errPositionalArgs, fs.Arg(0), fs.Arg(0))
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
	if err := writeLease(ctx, client, cfg.bucket, now, deadline, startNode); err != nil {
		return err
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
	if err := noArgs(fs); err != nil {
		return err
	}
	cfg, err := loadConfig(envBucket)
	if err != nil {
		return err
	}

	// Expire the lease rather than shrinking the pool here. L1 then drains
	// gracefully and L2 stops the pool -- which keeps "one writer per object" and
	// keeps the ordering that saves the running actors.
	now := time.Now()
	if err := writeLease(ctx, gcp.New(), cfg.bucket, now, now, false); err != nil {
		return err
	}
	fmt.Println("lease expired; the drain will run and the pool will stop")
	return nil
}

// errLeaseMoved is a lease write that lost to another write of lease.json.
var errLeaseMoved = errors.New("the lease changed while this command was running; re-run it")

// writeLease is every L0 write of lease.json: read it for its generation and
// wokenAt, then write the new deadline conditional on that generation, so two
// operators racing means one of them is told, rather than one silently losing.
//
// A wake writes wokenAt: a new session, which restarts L1's idle clock. Extend
// and sleep carry it over unchanged -- an extend is not a new session (the
// model's finding 3).
func writeLease(ctx context.Context, client *gcp.Client, bucket string, now, deadline time.Time, wake bool) error {
	body, generation, err := client.GetObject(ctx, bucket, ops.LeaseObject)
	var current lease.Lease
	switch {
	case err == nil:
		// A lease this command cannot parse still has a generation to write
		// over; its wokenAt is simply unknown.
		_ = json.Unmarshal(body, &current)
	case errors.Is(err, gcp.ErrNotFound):
		generation = 0 // create-only
	default:
		return fmt.Errorf("reading the lease: %w", err)
	}

	next := lease.Lease{Deadline: deadline, WokenAt: current.WokenAt}
	if wake {
		next.WokenAt = now
	}
	out, err := json.Marshal(next)
	if err != nil {
		return err
	}
	if err := client.PutObject(ctx, bucket, ops.LeaseObject, out, generation); err != nil {
		if errors.Is(err, gcp.ErrPreconditionFailed) {
			return errLeaseMoved
		}
		return fmt.Errorf("writing the lease: %w", err)
	}
	return nil
}

// --- the wrappers' check: may-start ---------------------------------------------

// errRefused is a check that said no. `run` exits 3 on it, so ax-job and ax-exec
// can tell "not now" from "broken".
var errRefused = errors.New("refused")

func cmdMayStart(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("may-start", flag.ExitOnError)
	need := fs.Duration("need", 10*time.Minute, "how long the lease must still run")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if err := noArgs(fs); err != nil {
		return err
	}
	cfg, err := loadConfig(envBucket)
	if err != nil {
		return err
	}
	ok, why, err := mayStart(ctx, gcp.New(), cfg.bucket, time.Now(), *need)
	if err != nil {
		return err
	}
	if !ok {
		return fmt.Errorf("%w: %s", errRefused, why)
	}
	fmt.Println("may start")
	return nil
}

// mayStart is lease.MayStartTask on what GCS holds now, plus the wrappers' own
// question: does the lease still run for `need`? A drain record it cannot read
// is an error, never "no drain": a wrapper must not start work it cannot see is
// safe to start.
func mayStart(ctx context.Context, client *gcp.Client, bucket string, now time.Time, need time.Duration) (bool, string, error) {
	l, leaseOK := ops.LeaseFromRead(client.GetObject(ctx, bucket, ops.LeaseObject))

	var d lease.Drain
	switch body, _, err := client.GetObject(ctx, bucket, ops.DrainObject); {
	case errors.Is(err, gcp.ErrNotFound):
	case err != nil:
		return false, "", fmt.Errorf("reading %s: %w", ops.DrainObject, err)
	default:
		if err := json.Unmarshal(body, &d); err != nil {
			return false, "", fmt.Errorf("%s is not a drain record: %w", ops.DrainObject, err)
		}
	}

	if ok, reason := lease.MayStartTask(now, l, leaseOK, d); !ok {
		return false, string(reason), nil
	}
	if left := l.Deadline.Sub(now); left < need {
		return false, fmt.Sprintf("the lease has %s left, and this needs %s (just exe-extend)", left.Round(time.Second), need), nil
	}
	return true, "", nil
}

// --- keep.json -----------------------------------------------------------------------

// errKeepMoved is a keep.json write that lost to another write of it.
var errKeepMoved = errors.New("keep.json changed while this command was running; re-run it")

func cmdKeep(ctx context.Context, args []string) error {
	cfg, err := loadConfig(envBucket)
	if err != nil {
		return err
	}
	client := gcp.New()
	switch {
	case len(args) == 1 && args[0] == "ls":
		tasks, err := keepList(ctx, client, cfg.bucket)
		if err != nil {
			return err
		}
		for _, task := range tasks {
			fmt.Println(task)
		}
		return nil
	case len(args) == 2 && (args[0] == "add" || args[0] == "rm"):
		return keepEdit(ctx, client, cfg.bucket, args[1], args[0] == "add")
	default:
		return errors.New("usage: exe-reaper keep add|rm TASK, or keep ls")
	}
}

func readKeep(ctx context.Context, client *gcp.Client, bucket string) (ops.Keep, int64, error) {
	body, generation, err := client.GetObject(ctx, bucket, ops.KeepObject)
	switch {
	case errors.Is(err, gcp.ErrNotFound):
		return ops.Keep{}, 0, nil
	case err != nil:
		return ops.Keep{}, 0, fmt.Errorf("reading %s: %w", ops.KeepObject, err)
	}
	var rec ops.Keep
	if err := json.Unmarshal(body, &rec); err != nil {
		return ops.Keep{}, 0, fmt.Errorf("%s is not a keep list: %w", ops.KeepObject, err)
	}
	return rec, generation, nil
}

// keepList is the exempted tasks, sorted; none when keep.json does not exist.
func keepList(ctx context.Context, client *gcp.Client, bucket string) ([]string, error) {
	rec, _, err := readKeep(ctx, client, bucket)
	if err != nil {
		return nil, err
	}
	slices.Sort(rec.Tasks)
	return slices.Compact(rec.Tasks), nil
}

// keepEdit adds or removes one task, conditional on the generation it read.
// Either way the end state is what was asked for, so repeating it is harmless.
func keepEdit(ctx context.Context, client *gcp.Client, bucket, task string, add bool) error {
	if task == "" {
		return errors.New("keep: empty task name")
	}
	rec, generation, err := readKeep(ctx, client, bucket)
	if err != nil {
		return err
	}
	tasks := slices.DeleteFunc(slices.Clone(rec.Tasks), func(t string) bool { return t == task })
	if add {
		tasks = append(tasks, task)
	}
	slices.Sort(tasks)
	body, err := json.Marshal(ops.Keep{Tasks: slices.Compact(tasks)})
	if err != nil {
		return err
	}
	if err := client.PutObject(ctx, bucket, ops.KeepObject, body, generation); err != nil {
		if errors.Is(err, gcp.ErrPreconditionFailed) {
			return errKeepMoved
		}
		return fmt.Errorf("writing %s: %w", ops.KeepObject, err)
	}
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
	if err := noArgs(fs); err != nil {
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
	obs.Lease, obs.LeaseOK = ops.LeaseFromRead(client.GetObject(ctx, cfg.bucket, ops.LeaseObject))

	if drainBody, _, derr := client.GetObject(ctx, cfg.bucket, ops.DrainObject); derr == nil {
		var d lease.Drain
		if json.Unmarshal(drainBody, &d) == nil {
			obs.Drain = d
		}
	}

	pool, sizeErr := client.NodePool(ctx, cfg.project, cfg.zone, cfg.cluster, cfg.nodePool)
	if sizeErr != nil {
		e.log.warn(fmt.Sprintf("node pool size unreadable, deciding as if a node may be up: %v", sizeErr))
	}
	obs.Nodes = nodesForDecision(pool.Target, sizeErr)

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

	// The stop-latency detector (inbox M18, layer 3). With the pool unreadable
	// there is nothing to judge, so the memory is carried as it was.
	stoppingSince, stopPaged := prev.StoppingSince, prev.StopLatencyPaged
	if sizeErr == nil {
		var alarm bool
		stoppingSince, alarm = lease.NextStopping(prev.StoppingSince, pool.Target, pool.Instances, now)
		if alarm {
			// Once per stop: the first alarm of a stop pages, the rest repeat.
			notify := !prev.StopLatencyPaged.Equal(stoppingSince)
			e.log.stopLatency(now, stoppingSince, pool, notify)
			stopPaged = stoppingSince
		}
	}

	if recordErr != nil {
		// No generation to write against, so a conditional write could only
		// lose to the record that is there. Fail the tick instead: the job
		// exits non-zero, and the failed-execution alert says so.
		return fmt.Errorf("not recording this tick: %w", recordErr)
	}

	record := enforceRecord{
		At:               now,
		Action:           string(decision.Action),
		Reason:           string(decision.Reason),
		Notified:         line.Notify,
		ReadFailures:     obs.ConsecutiveReadFailures,
		LeaseGeneration:  key,
		StoppingSince:    stoppingSince,
		StopLatencyPaged: stopPaged,
	}
	body, err := json.Marshal(record)
	if err != nil {
		return err
	}
	// Conditional on the generation L2 itself last saw. Two enforcer executions
	// overlapping (a retry, a manual run) then produce one winner rather than a
	// silently interleaved record.
	err = client.PutObject(ctx, cfg.bucket, ops.EnforceObject, body, prevGeneration)
	switch {
	case errors.Is(err, gcp.ErrPreconditionFailed):
		e.log.warn(ops.EnforceObject + " changed during this tick; the other execution's record stands")
	case err != nil:
		return fmt.Errorf("writing the enforcement record: %w", err)
	}
	return nil
}

// leaseMoved reads lease.json again and reports whether it has moved since the
// observation: a new generation, or, for a decision taken blind, a lease that
// can be read at all. A read that fails is no evidence that anything moved.
func (e enforcer) leaseMoved(ctx context.Context, obs lease.Observation) (bool, lease.Lease) {
	current, ok := ops.LeaseFromRead(e.client.GetObject(ctx, e.cfg.bucket, ops.LeaseObject))
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
// read is what lets a run of blind stops count as one.
func pageKey(obs lease.Observation, prev enforceRecord) int64 {
	if obs.LeaseOK {
		return obs.Lease.Generation
	}
	return prev.LeaseGeneration
}

// shouldPage reports whether a decision pages the operator: a forced stop,
// unless the tick right before it was a forced stop under the same key (D4).
//
// The stop is repeated on every tick that sees the pool up -- setSize(0) is
// idempotent -- and a stuck stop, or a pool size that keeps reading as up,
// would otherwise page on every tick all night. Any other tick in between (the
// pool found at zero, a wait) ends the run, and the next forced stop pages.
// Keying on the lease generation alone, as this once did, took a new wake whose
// lease L2 never read for a repeat of the last stop, and stopped it in silence.
func shouldPage(d lease.Decision, key int64, prev enforceRecord) bool {
	if !d.Notify() {
		return false
	}
	repeat := prev.Action == string(lease.ActionStopForced) && prev.LeaseGeneration == key
	return !repeat
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
//	          notify is set -- a forced stop that is not a repeat of the
//	          tick before (shouldPage), which the forced-stop alert pages
//	          on. A repeat is WARNING.
//	failure   event "failure" at ERROR, the last line before exit 1. The
//	          failed-execution alert pages on ERROR that is not a decision.
//	stop-     event "stop-latency": the pool's target has been zero for
//	latency   longer than lease.StopLatency and an instance is still there,
//	          billing. ERROR the first time for a stop, which the stop-latency
//	          alert pages on; WARNING on every later tick of the same stop. The
//	          failed-execution alert excludes it by this event name.
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

type stopLatencyFields struct {
	Event         string    `json:"event"`
	Notify        bool      `json:"notify"`
	Target        int       `json:"target"`
	Instances     int       `json:"instances"`
	StoppingSince time.Time `json:"stoppingSince"`
}

// stopLatency reports a node that still bills past the stop latency.
func (l contractLog) stopLatency(now, since time.Time, pool gcp.Pool, notify bool) {
	severity := severityWarning
	if notify {
		severity = severityError
	}
	l.write(logEntry{
		Severity: severity,
		Message: fmt.Sprintf("the node pool's target has been zero for %s, past the %s stop latency, and %d instance(s) still bill",
			now.Sub(since).Round(time.Second), lease.StopLatency, pool.Instances),
		L2: stopLatencyFields{
			Event: "stop-latency", Notify: notify, Target: pool.Target,
			Instances: pool.Instances, StoppingSince: since,
		},
	})
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
	// StoppingSince is the first tick that found the pool's target at zero
	// with an instance still there; zero when there is none (NextStopping).
	StoppingSince time.Time `json:"stoppingSince,omitzero"`
	// StopLatencyPaged is the StoppingSince of the stop last paged for, so
	// one slow stop pages once.
	StopLatencyPaged time.Time `json:"stopLatencyPaged,omitzero"`
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
	body, generation, err := client.GetObject(ctx, bucket, ops.EnforceObject)
	switch {
	case errors.Is(err, gcp.ErrNotFound):
		return enforceRecord{}, 0, nil
	case err != nil:
		return enforceRecord{}, 0, fmt.Errorf("reading %s: %w", ops.EnforceObject, err)
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
	if err := noArgs(fs); err != nil {
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

	switch body, generation, err := client.GetObject(ctx, cfg.bucket, ops.LeaseObject); {
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

	if body, _, err := client.GetObject(ctx, cfg.bucket, ops.DrainObject); err == nil {
		var d lease.Drain
		if json.Unmarshal(body, &d) == nil {
			fmt.Printf("drain          %s\n", describeDrain(d))
		}
	} else {
		fmt.Println("drain          (none)")
	}

	rec, _, recErr := readEnforce(ctx, client, cfg.bucket)
	switch {
	case recErr != nil:
		fmt.Printf("last enforce   unreadable: %v\n", recErr)
	case rec.Action != "":
		fmt.Printf("last enforce   %s (%s) at %s\n", rec.Action, rec.Reason,
			rec.At.In(lease.Location()).Format(time.RFC3339))
	default:
		fmt.Println("last enforce   (none)")
	}

	// The target is what setSize asked for; instances are what still bills. A
	// target of zero with an instance left is a stop in progress -- and past
	// the stop latency, the Phase 4 incident (inbox M18, layer 3).
	if pool, err := client.NodePool(ctx, cfg.project, cfg.zone, cfg.cluster, cfg.nodePool); err == nil {
		fmt.Printf("node pool      %d node(s) (target %d)\n", pool.Instances, pool.Target)
		if pool.Target == 0 && pool.Instances > 0 {
			line := "stopping       the node still bills"
			if recErr == nil && !rec.StoppingSince.IsZero() {
				line += fmt.Sprintf(" (seen since %s, stop latency %s)",
					rec.StoppingSince.In(lease.Location()).Format(time.RFC3339), lease.StopLatency)
			}
			fmt.Println(line)
		}
		if pool.Instances == 0 {
			fmt.Println("tasks          (asleep — task counts need the cluster up)")
		}
	} else {
		fmt.Printf("node pool      unreadable: %v\n", err)
	}

	// tasks.json is L1's record: it answers while the node sleeps, as of the
	// last time L1 saw a change.
	if body, _, err := client.GetObject(ctx, cfg.bucket, ops.TasksObject); err == nil {
		var rec lease.TasksRecord
		if json.Unmarshal(body, &rec) == nil {
			fmt.Printf("tasks          %d as L1 last saw them (%s)\n",
				len(rec.Tasks), rec.At.In(lease.Location()).Format(time.RFC3339))
			for _, line := range ttlNotice(rec, now) {
				fmt.Println("task TTL       " + line)
			}
		}
	}

	if kept, err := keepList(ctx, client, cfg.bucket); err != nil {
		fmt.Printf("kept tasks     unreadable: %v\n", err)
	} else if len(kept) > 0 {
		fmt.Printf("kept tasks     %s (exempt from the %s task TTL)\n", strings.Join(kept, ", "), lease.TaskTTL)
	}

	fmt.Printf("nightly cap    %02d:00 %s, daily stop %02d:00\n",
		lease.NightlyCapHour, lease.TimezoneName, lease.L3StopHour)
	return nil
}

// describeDrain is drain.json for a reader: what the phase means, and only
// the fields that mean something in it.
func describeDrain(d lease.Drain) string {
	stamp := func(t time.Time) string { return t.In(lease.Location()).Format(time.RFC3339) }
	if d.Phase == lease.DrainNone {
		if d.IdleSince.IsZero() {
			return "none"
		}
		return "none (nothing awake since " + stamp(d.IdleSince) + ")"
	}
	phase := string(d.Phase)
	if d.Failure != "" {
		phase += " (" + d.Failure + ")"
	}
	if d.Reason != "" {
		phase += " for " + string(d.Reason)
	}
	return fmt.Sprintf("%s (heartbeat %s, lease generation %d)", phase, stamp(d.Heartbeat), d.LeaseGeneration)
}

// ttlNotice is exe-status's warning about the task TTL (plan D10): each
// suspended, unkept task whose TTL runs out within TaskTTLWarning, or already
// has. L1 deletes it at the first wake after that, so the notice is how the
// operator hears of it in time to keep it.
func ttlNotice(rec lease.TasksRecord, now time.Time) []string {
	var out []string
	for _, t := range rec.Tasks {
		if !t.Suspended || t.Kept || t.DeleteAt.IsZero() || t.DeleteAt.Sub(now) > lease.TaskTTLWarning {
			continue
		}
		keep := " (keep it: just exe-keep add " + t.Task + ")"
		if !now.Before(t.DeleteAt) {
			out = append(out, t.Task+" is past its TTL and is deleted at the next wake"+keep)
			continue
		}
		out = append(out, t.Task+" is deleted at the first wake after "+
			t.DeleteAt.In(lease.Location()).Format(time.RFC3339)+keep)
	}
	slices.Sort(out)
	return out
}
