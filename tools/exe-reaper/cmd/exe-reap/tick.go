package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"time"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/ax"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/gcp"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/k8s"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/lease"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/ops"
)

// The two Deployments whose replica counts L1 owns (plan D2): the router that
// auto-resumes an actor on a connection, and the controller that carries out
// every AX resume. tofu/exe-cluster grants the reaper get and patch on exactly
// their scale subresources, and nothing else in their namespaces.
const (
	routerNamespace      = "ate-system"
	routerDeployment     = "atenet-router"
	controllerNamespace  = "ax-system"
	controllerDeployment = "ax-controller"
)

// What the tick reads and does, one interface per client. Each client is
// tested on the wire against a real server of its kind; the tick's tests fake
// at these seams to test the tick.
type (
	actorSource interface {
		Actors(ctx context.Context) ([]lease.ActorObs, error)
		TemplatesPending(ctx context.Context) (bool, error)
	}
	axAPI interface {
		Suspend(ctx context.Context, task string) error
		Tasks(ctx context.Context) ([]ax.Task, error)
		Delete(ctx context.Context, task string) error
	}
	tagStore interface {
		ListPackages(ctx context.Context, repo string) ([]string, error)
		ListTags(ctx context.Context, pkg string) ([]gcp.ARTag, error)
		CreateTag(ctx context.Context, pkg, id, digest string) error
		DeleteTag(ctx context.Context, pkg, id string) error
	}
	clusterAPI interface {
		Scale(ctx context.Context, ns, deployment string) (int, string, error)
		SetScale(ctx context.Context, ns, deployment string, replicas int) error
		CountPods(ctx context.Context, ns, selector string) (int, error)
		PodImages(ctx context.Context, ns string) ([]string, error)
		DeletePod(ctx context.Context, ns, name, uid string) error
	}
	objectStore interface {
		GetObject(ctx context.Context, bucket, object string) ([]byte, int64, error)
		PutObject(ctx context.Context, bucket, object string, data []byte, ifGeneration int64) error
	}
)

// reaper is L1: one tick per CronJob run.
type reaper struct {
	substrate actorSource
	ax        axAPI
	k8s       clusterAPI
	gcs       objectStore
	ar        tagStore
	bucket    string
	// repos are the Artifact Registry repositories whose images retention
	// protects, by resource name (projects/P/locations/L/repositories/R).
	repos []string
	// podNamespaces are the namespaces whose pods' images retention protects
	// like a task's (the cluster's own workloads); protect names the images
	// it protects that run outside the cluster, pinned by digest.
	podNamespaces []string
	protect       []string
	log           l1Log
	// dryRun decides and logs, and writes and does nothing.
	dryRun bool
}

// tick is one L1 run: observe everything, decide (lease.DecideL1), record the
// decision in drain.json, and only then act on it.
//
// The order is the design (plan D2):
//   - Actors and templates first, the lease after: the baseline of a drain
//     begun this tick is complete before the lease is read, so a crash during
//     the listing precedes the drain and anything later counts against it.
//   - Nothing is decided on a partial view. Any read that fails, except the
//     lease's (an unreadable lease is itself a trigger), fails the tick.
//   - The record is written before anything is done, conditional on the
//     generation read. A write that loses the race does nothing: its decision
//     was about a record that no longer stands. A failed action fails the tick
//     but leaves the record, and the next tick does it again, because every
//     decision is a target state.
func (r *reaper) tick(ctx context.Context, now time.Time) error {
	obs, drainGen, err := r.observe(ctx, now)
	if err != nil {
		r.log.fail(err)
		return err
	}
	d := lease.DecideL1(obs)
	r.log.decision(obs, d, r.dryRun)
	if r.dryRun {
		return nil
	}

	switch err := r.record(ctx, obs.Drain, d.Drain, drainGen); {
	case errors.Is(err, gcp.ErrPreconditionFailed):
		r.log.warn(ops.DrainObject + " changed during this tick; acting on nothing, the next tick decides again")
		return nil
	case err != nil:
		err = fmt.Errorf("recording the decision: %w", err)
		r.log.fail(err)
		return err
	}

	if err := r.act(ctx, obs, d); err != nil {
		r.log.fail(err)
		return err
	}

	// Retention has the tick only when the drain does not: no trigger, so no
	// drain in flight and none starting.
	switch d.Branch {
	case lease.L1NoOp, lease.L1Reopen, lease.L1Cancel:
		if err := r.retain(ctx, now, obs.Actors); err != nil {
			err = fmt.Errorf("retention: %w", err)
			r.log.fail(err)
			return err
		}
	}
	return nil
}

// observe reads everything the decision needs, in the order tick documents,
// and the generation of drain.json for the conditional write.
func (r *reaper) observe(ctx context.Context, now time.Time) (lease.L1Observation, int64, error) {
	obs := lease.L1Observation{Now: now}
	var err error
	if obs.Actors, err = r.substrate.Actors(ctx); err != nil {
		return obs, 0, err
	}
	if obs.TemplatesPending, err = r.substrate.TemplatesPending(ctx); err != nil {
		return obs, 0, err
	}
	if obs.RouterReplicas, obs.RouterPods, err = r.deployment(ctx, routerNamespace, routerDeployment); err != nil {
		return obs, 0, err
	}
	if obs.ControllerReplicas, obs.ControllerPods, err = r.deployment(ctx, controllerNamespace, controllerDeployment); err != nil {
		return obs, 0, err
	}
	obs.Lease, obs.LeaseOK = ops.LeaseFromRead(r.gcs.GetObject(ctx, r.bucket, ops.LeaseObject))

	body, generation, err := r.gcs.GetObject(ctx, r.bucket, ops.DrainObject)
	switch {
	case errors.Is(err, gcp.ErrNotFound):
		// The first tick ever: no record, and generation 0 so the write
		// creates it.
		return obs, 0, nil
	case err != nil:
		return obs, 0, fmt.Errorf("reading %s: %w", ops.DrainObject, err)
	}
	// A record L1 cannot read is one whose baseline it cannot trust. Deciding
	// from "no drain" would take a new baseline over crashes the lost one
	// counted, and call them graceful. So the tick fails, and keeps failing,
	// until the operator deletes the object; L2 forces meanwhile.
	if err := json.Unmarshal(body, &obs.Drain); err != nil {
		return obs, 0, fmt.Errorf("%s is not a drain record (delete it to start over): %w", ops.DrainObject, err)
	}
	return obs, generation, nil
}

// deployment is one Deployment's replica count and the pods behind it that
// can still run -- a terminating one included, since it serves until it is
// gone.
func (r *reaper) deployment(ctx context.Context, ns, name string) (int, int, error) {
	replicas, selector, err := r.k8s.Scale(ctx, ns, name)
	if err != nil {
		return 0, 0, err
	}
	pods, err := r.k8s.CountPods(ctx, ns, selector)
	if err != nil {
		return 0, 0, err
	}
	return replicas, pods, nil
}

// record writes drain.json if this tick changed it.
func (r *reaper) record(ctx context.Context, before, after lease.Drain, generation int64) error {
	was, err := json.Marshal(before)
	if err != nil {
		return err
	}
	now, err := json.Marshal(after)
	if err != nil {
		return err
	}
	if string(was) == string(now) {
		return nil
	}
	return r.gcs.PutObject(ctx, r.bucket, ops.DrainObject, now, generation)
}

// act moves the cluster to the decision's target state. Everything is tried;
// what it works around is a warning, and anything else fails the tick.
func (r *reaper) act(ctx context.Context, obs lease.L1Observation, d lease.L1Decision) error {
	var errs []error
	if d.RouterReplicas != obs.RouterReplicas {
		errs = append(errs, r.k8s.SetScale(ctx, routerNamespace, routerDeployment, d.RouterReplicas))
	}
	if d.ControllerReplicas != obs.ControllerReplicas {
		errs = append(errs, r.k8s.SetScale(ctx, controllerNamespace, controllerDeployment, d.ControllerReplicas))
	}
	for _, task := range d.Suspend {
		err := r.ax.Suspend(ctx, task)
		if errors.Is(err, ax.ErrNoTask) {
			// Its actor stays awake, so the drain waits on it; the ceiling
			// is what ends that, as a drain-failed L2 forces and pages.
			r.log.warn(fmt.Sprintf("%v: its actor stays awake, and the drain cannot finish while it does", err))
			continue
		}
		errs = append(errs, err)
	}
	for _, worker := range d.ClearWorkers {
		ns, pod, uid, ok := splitWorker(worker)
		if !ok {
			errs = append(errs, fmt.Errorf("worker %q is not <namespace>/<pod>/<uid>", worker))
			continue
		}
		err := r.k8s.DeletePod(ctx, ns, pod, uid)
		if errors.Is(err, k8s.ErrPodReplaced) {
			r.log.warn(fmt.Sprintf("%v: not deleted", err))
			continue
		}
		errs = append(errs, err)
	}
	return errors.Join(errs...)
}

// splitWorker parses substrate's "<namespace>/<pod>/<pod uid>".
func splitWorker(worker string) (ns, pod, uid string, ok bool) {
	parts := strings.Split(worker, "/")
	if len(parts) != 3 || parts[0] == "" || parts[1] == "" || parts[2] == "" {
		return "", "", "", false
	}
	return parts[0], parts[1], parts[2], true
}

// --- the log contract -------------------------------------------------------------
//
// `exe-reap` writes one JSON object per line to stdout, and nothing else. GKE
// lifts "severity" into the entry's level and "message" into its summary; the
// rest lands in jsonPayload, L1's fields under jsonPayload.exe_l1:
//
//	decision  event "decision", once per tick that decided: the branch, the
//	          record it leaves, what it saw and what it asks for. INFO when
//	          nothing changed hands, NOTICE when the tick moved something,
//	          WARNING when a drain failed. L2 forces and pages on a failed
//	          drain, so this line is the reader's why, not a second page.
//	retention event "retention" at NOTICE: what the retention step deleted,
//	          tagged and released, when it did anything (plan D10).
//	warning   event "warning" at WARNING: something the tick worked around.
//	failure   event "failure" at ERROR: the tick could not read, record or
//	          act; the last line before exit 1.

const (
	severityInfo    = "INFO"
	severityNotice  = "NOTICE"
	severityWarning = "WARNING"
	severityError   = "ERROR"
)

type l1Log struct {
	w io.Writer
}

type logEntry struct {
	Severity string `json:"severity"`
	Message  string `json:"message"`
	L1       any    `json:"exe_l1"`
}

func (l l1Log) write(e logEntry) {
	body, err := json.Marshal(e)
	if err != nil {
		body = fmt.Appendf(nil, `{"severity":%q,"message":%q,"exe_l1":{"event":"failure"}}`, e.Severity, e.Message)
	}
	_, _ = l.w.Write(append(body, '\n'))
}

type decisionFields struct {
	Event            string   `json:"event"`
	Branch           string   `json:"branch"`
	Phase            string   `json:"phase"`
	Reason           string   `json:"reason,omitempty"`
	Failure          string   `json:"failure,omitempty"`
	DryRun           bool     `json:"dryRun,omitempty"`
	LeaseReadable    bool     `json:"leaseReadable"`
	LeaseGeneration  int64    `json:"leaseGeneration"`
	Actors           int      `json:"actors"`
	Awake            int      `json:"awake"`
	TemplatesPending bool     `json:"templatesPending"`
	Router           int      `json:"router"`
	Controller       int      `json:"controller"`
	RouterPods       int      `json:"routerPods"`
	ControllerPods   int      `json:"controllerPods"`
	Suspend          []string `json:"suspend,omitempty"`
	Cleared          []string `json:"cleared,omitempty"`
}

func (l l1Log) decision(obs lease.L1Observation, d lease.L1Decision, dryRun bool) {
	awake := 0
	for _, a := range obs.Actors {
		if a.State == lease.ActorAwake || a.State == lease.ActorCheckpointing {
			awake++
		}
	}
	severity := severityInfo
	switch d.Branch {
	case lease.L1NoOp, lease.L1Settled, lease.L1Wait:
	case lease.L1Lost, lease.L1GiveUp:
		severity = severityWarning
	default:
		severity = severityNotice
	}
	l.write(logEntry{
		Severity: severity,
		Message: fmt.Sprintf("L1 %s: drain %s, %d of %d actors awake, router %d, controller %d",
			d.Branch, phaseName(d.Drain.Phase), awake, len(obs.Actors), d.RouterReplicas, d.ControllerReplicas),
		L1: decisionFields{
			Event:            "decision",
			Branch:           string(d.Branch),
			Phase:            string(d.Drain.Phase),
			Reason:           string(d.Drain.Reason),
			Failure:          d.Drain.Failure,
			DryRun:           dryRun,
			LeaseReadable:    obs.LeaseOK,
			LeaseGeneration:  obs.Lease.Generation,
			Actors:           len(obs.Actors),
			Awake:            awake,
			TemplatesPending: obs.TemplatesPending,
			Router:           d.RouterReplicas,
			Controller:       d.ControllerReplicas,
			RouterPods:       obs.RouterPods,
			ControllerPods:   obs.ControllerPods,
			Suspend:          d.Suspend,
			Cleared:          d.ClearWorkers,
		},
	})
}

func phaseName(p lease.DrainPhase) string {
	if p == lease.DrainNone {
		return "none"
	}
	return string(p)
}

type messageFields struct {
	Event string `json:"event"`
	Error string `json:"error,omitempty"`
}

type retentionFields struct {
	Event    string   `json:"event"`
	Deleted  []string `json:"deleted,omitempty"`
	Tagged   []string `json:"tagged,omitempty"`
	Untagged []string `json:"untagged,omitempty"`
}

// retention reports a retention step that deleted, tagged or untagged
// something. A step that changed nothing writes no line.
func (l l1Log) retention(d lease.RetentionDecision) {
	f := retentionFields{Event: "retention", Deleted: d.Delete}
	for _, img := range d.Tag {
		f.Tagged = append(f.Tagged, img.Key())
	}
	for _, tag := range d.Untag {
		f.Untagged = append(f.Untagged, tag.Image.Key()+" "+tag.Name)
	}
	l.write(logEntry{
		Severity: severityNotice,
		Message: fmt.Sprintf("L1 retention: %d task(s) past their TTL deleted, %d image(s) tagged, %d tag(s) released",
			len(f.Deleted), len(f.Tagged), len(f.Untagged)),
		L1: f,
	})
}

func (l l1Log) warn(message string) {
	l.write(logEntry{Severity: severityWarning, Message: message, L1: messageFields{Event: "warning"}})
}

func (l l1Log) fail(err error) {
	l.write(logEntry{
		Severity: severityError,
		Message:  "exe-reap failed: " + err.Error(),
		L1:       messageFields{Event: "failure", Error: err.Error()},
	})
}
