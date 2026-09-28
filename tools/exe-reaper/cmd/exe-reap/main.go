// Command exe-reap is L1, the in-cluster reaper: one tick per run of its
// CronJob, every minute (docs/plan/exe-google-ax.md section 3.2, Phase 6 plan
// D2).
//
// A tick reads every actor through Substrate, the router's and the
// controller's replica counts and pods through the Kubernetes API, the lease
// and its own drain record from the ops bucket; decides with lease.DecideL1;
// writes drain.json, conditional on the generation it read; and only then
// acts: scales the two Deployments, asks AX to suspend awake tasks, deletes a
// wedged worker's pod. L1 never touches the node pool. The pool is L2's.
//
// This binary is the only one in the module that links gRPC, for the AX and
// Substrate stubs (plan D1). exe-reaper, which shrinks the pool, links the
// standard library and this module only, and deps_test.go keeps it so.
//
// Configuration comes from the environment the CronJob sets
// (tofu/exe-cluster), with the in-cluster defaults the ax-controller uses for
// the same endpoints.
//
// One subcommand runs something else: `exe-reap snapshot-gc`, the operator's
// orphan-snapshot GC (snapshotgc.go), in a one-off Job from the same template.
package main

import (
	"context"
	"flag"
	"fmt"
	"io"
	"os"
	"strings"
	"time"

	"github.com/hironow/dotfiles/tools/exe-reaper/internal/ax"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/gcp"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/k8s"
	"github.com/hironow/dotfiles/tools/exe-reaper/internal/substrate"
)

const (
	envBucket          = "EXE_OPS_BUCKET"
	envARRepos         = "EXE_AR_REPOS"
	envSubstrateTarget = "EXE_SUBSTRATE_TARGET"
	envSubstrateToken  = "EXE_SUBSTRATE_TOKEN_FILE" //nolint:gosec // G101: env var name, not a credential
	envSubstrateCA     = "EXE_SUBSTRATE_CA_FILE"
	envAXTarget        = "EXE_AX_TARGET"

	defaultSubstrateTarget = "api.ate-system.svc.cluster.local:443"
	defaultSubstrateToken  = "/var/run/secrets/ateapi/token" //nolint:gosec // G101: path of the projected token file, not a credential
	defaultSubstrateCA     = "/run/servicedns-ca/trust-bundle.pem"
	defaultAXTarget        = "ax-server.ax-system.svc.cluster.local:8080"

	// tickTimeout ends a tick well inside its one-minute schedule, so a
	// stuck call cannot hold the next run back (the CronJob forbids overlap).
	tickTimeout = 45 * time.Second
)

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

func run(args []string, stdout, stderr io.Writer) int {
	if len(args) > 0 && args[0] == "snapshot-gc" {
		return runSnapshotGC(args[1:], stdout, stderr)
	}
	fs := flag.NewFlagSet("exe-reap", flag.ContinueOnError)
	fs.SetOutput(stderr)
	dryRun := fs.Bool("dry-run", false, "decide and log, but write and do nothing")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if fs.NArg() != 0 {
		fmt.Fprintf(stderr, "exe-reap takes no arguments besides the snapshot-gc subcommand, got %q\n", fs.Args())
		return 2
	}

	r, closeAll, err := wire(stdout)
	if err != nil {
		l1Log{w: stdout}.fail(err)
		return 1
	}
	defer closeAll()
	r.dryRun = *dryRun

	ctx, cancel := context.WithTimeout(context.Background(), tickTimeout)
	defer cancel()
	if err := r.tick(ctx, time.Now()); err != nil {
		return 1
	}
	return 0
}

// wire builds a reaper with the real clients from the environment.
func wire(stdout io.Writer) (*reaper, func(), error) {
	bucket := os.Getenv(envBucket)
	if bucket == "" {
		return nil, nil, fmt.Errorf("missing required environment: %s", envBucket)
	}
	// Without them retention would protect nothing, and Artifact Registry's
	// cleanup would take the images of suspended tasks: refuse instead.
	repos := splitList(os.Getenv(envARRepos))
	if len(repos) == 0 {
		return nil, nil, fmt.Errorf("missing required environment: %s", envARRepos)
	}
	sub, err := substrate.Dial(substrate.Options{
		Target:     envOr(envSubstrateTarget, defaultSubstrateTarget),
		ServerName: substrate.ServerName,
		TokenFile:  envOr(envSubstrateToken, defaultSubstrateToken),
		CAFile:     envOr(envSubstrateCA, defaultSubstrateCA),
	})
	if err != nil {
		return nil, nil, err
	}
	axc, err := ax.Dial(envOr(envAXTarget, defaultAXTarget))
	if err != nil {
		_ = sub.Close()
		return nil, nil, err
	}
	kube, err := k8s.InCluster()
	if err != nil {
		_ = sub.Close()
		_ = axc.Close()
		return nil, nil, err
	}
	closeAll := func() {
		_ = sub.Close()
		_ = axc.Close()
	}
	cloud := gcp.New()
	return &reaper{
		substrate: sub,
		ax:        axc,
		k8s:       kube,
		gcs:       cloud,
		ar:        cloud,
		bucket:    bucket,
		repos:     repos,
		log:       l1Log{w: stdout},
	}, closeAll, nil
}

// splitList reads a comma-separated list from the environment, such as
// EXE_AR_REPOS's repository resource names.
func splitList(raw string) []string {
	var out []string
	for _, r := range strings.Split(raw, ",") {
		if r = strings.TrimSpace(r); r != "" {
			out = append(out, r)
		}
	}
	return out
}

func envOr(name, fallback string) string {
	if v := os.Getenv(name); v != "" {
		return v
	}
	return fallback
}
