package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"slices"
	"strings"
	"time"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/ax"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/gcp"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/lease"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/ops"
)

// retain is L1's retention step (plan D10, exe/spec/retention.qnt): read every
// task, the images the cluster's own pods run and the ones configured as
// running elsewhere (M19 C3), the operator's keep list, the `inuse-` tags in
// the repositories L1 protects and its own record; decide with
// lease.DecideRetention; record; then act. Like the drain, it decides nothing
// on a partial view: a read that fails ends the step.
func (r *reaper) retain(ctx context.Context, now time.Time, actors []lease.ActorObs) error {
	o, generation, err := r.observeRetention(ctx, now, actors)
	if err != nil {
		return err
	}
	d := lease.DecideRetention(o)

	switch err := r.recordRetention(ctx, o.Record, d.Record, generation); {
	case errors.Is(err, gcp.ErrPreconditionFailed):
		r.log.warn(ops.TasksObject + " changed during this tick; acting on nothing, the next tick decides again")
		return nil
	case err != nil:
		return fmt.Errorf("recording %s: %w", ops.TasksObject, err)
	}

	var errs []error
	for _, task := range d.Delete {
		if err := r.ax.Delete(ctx, task); err != nil && !errors.Is(err, ax.ErrNoTask) {
			errs = append(errs, err)
		}
	}
	for _, img := range d.Tag {
		errs = append(errs, r.ar.CreateTag(ctx, img.Package, lease.L1TagName(img.Digest), img.Digest))
	}
	for _, tag := range d.Untag {
		errs = append(errs, r.ar.DeleteTag(ctx, tag.Image.Package, tag.Name))
	}
	if len(d.Delete)+len(d.Tag)+len(d.Untag) > 0 {
		r.log.retention(d)
	}
	return errors.Join(errs...)
}

// observeRetention reads what DecideRetention needs, and the generation of
// tasks.json for the conditional write.
func (r *reaper) observeRetention(ctx context.Context, now time.Time, actors []lease.ActorObs) (lease.RetentionObservation, int64, error) {
	o := lease.RetentionObservation{Now: now}

	tasks, err := r.ax.Tasks(ctx)
	if err != nil {
		return o, 0, err
	}
	byTask := map[string]lease.ActorObs{}
	for _, a := range actors {
		if !a.Golden {
			byTask[a.Task] = a
		}
	}
	for _, t := range tasks {
		obs := lease.TaskObs{Key: t.Key, Image: r.managedImage(t.Image)}
		if a, ok := byTask[t.Key]; ok && a.State == lease.ActorAtRest {
			obs.Suspended, obs.ChangedAt = true, a.ChangedAt
		}
		o.Tasks = append(o.Tasks, obs)
	}

	platform := slices.Clone(r.protect)
	for _, ns := range r.podNamespaces {
		refs, err := r.k8s.PodImages(ctx, ns)
		if err != nil {
			return o, 0, err
		}
		platform = append(platform, refs...)
	}
	seen := map[string]bool{}
	for _, ref := range platform {
		img := r.managedImage(ref)
		if img == (lease.Image{}) || seen[img.Key()] {
			continue
		}
		seen[img.Key()] = true
		o.Platform = append(o.Platform, img)
	}

	keep, err := r.readKeep(ctx)
	if err != nil {
		return o, 0, err
	}
	o.Keep = keep

	for _, repo := range r.repos {
		packages, err := r.ar.ListPackages(ctx, repo)
		if err != nil {
			return o, 0, err
		}
		for _, pkg := range packages {
			tags, err := r.ar.ListTags(ctx, pkg)
			if err != nil {
				return o, 0, err
			}
			for _, t := range tags {
				if strings.HasPrefix(t.ID, "inuse-") {
					o.Tags = append(o.Tags, lease.Tag{Name: t.ID, Image: lease.Image{Package: pkg, Digest: t.Digest}})
				}
			}
		}
	}

	body, generation, err := r.gcs.GetObject(ctx, r.bucket, ops.TasksObject)
	switch {
	case errors.Is(err, gcp.ErrNotFound):
		return o, 0, nil
	case err != nil:
		return o, 0, fmt.Errorf("reading %s: %w", ops.TasksObject, err)
	}
	// A record L1 cannot read is overwritten: it holds only release clocks,
	// and losing them keeps tags longer, never shorter. The TTL counts from
	// the store, not from here.
	if err := json.Unmarshal(body, &o.Record); err != nil {
		r.log.warn(fmt.Sprintf("%s is not a retention record, starting it over: %v", ops.TasksObject, err))
		o.Record = lease.TasksRecord{}
	}
	return o, generation, nil
}

// managedImage is the image a task runs, if it lives in a repository L1
// protects and is pinned by digest; the zero Image otherwise.
func (r *reaper) managedImage(ref string) lease.Image {
	repo, pkg, digest, ok := gcp.ParseImageRef(ref)
	if !ok || !slices.Contains(r.repos, repo) {
		return lease.Image{}
	}
	return lease.Image{Package: pkg, Digest: digest}
}

func (r *reaper) readKeep(ctx context.Context) ([]string, error) {
	body, _, err := r.gcs.GetObject(ctx, r.bucket, ops.KeepObject)
	switch {
	case errors.Is(err, gcp.ErrNotFound):
		return nil, nil
	case err != nil:
		return nil, fmt.Errorf("reading %s: %w", ops.KeepObject, err)
	}
	var keep ops.Keep
	// Unlike tasks.json, the operator's keep list is not L1's to start over:
	// guessing it empty could delete a kept task.
	if err := json.Unmarshal(body, &keep); err != nil {
		return nil, fmt.Errorf("%s is not a keep list: %w", ops.KeepObject, err)
	}
	return keep.Tasks, nil
}

// recordRetention writes tasks.json when its contents changed; the time of
// the tick alone is not a change.
func (r *reaper) recordRetention(ctx context.Context, before, after lease.TasksRecord, generation int64) error {
	untimed := func(rec lease.TasksRecord) ([]byte, error) {
		rec.At = time.Time{}
		return json.Marshal(rec)
	}
	was, err := untimed(before)
	if err != nil {
		return err
	}
	now, err := untimed(after)
	if err != nil {
		return err
	}
	if string(was) == string(now) {
		return nil
	}
	body, err := json.Marshal(after)
	if err != nil {
		return err
	}
	return r.gcs.PutObject(ctx, r.bucket, ops.TasksObject, body, generation)
}
