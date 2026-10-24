// brotli-doctor inventories native CLI images without executing them.
// It reports Brotli evidence and uncertainty, never a clean bill of health.
package main

import (
	"context"
	"encoding/json/v2"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"
)

const (
	disclaimer = "Evidence inventory only, NOT a security clearance. UNKNOWN does not mean absent. Direct imports only; dlopen, transitive libraries, stripped/static code and CVE applicability require further review."
	help       = `usage: brotli-doctor [--json] [--mise=false] [--path=false] [--max-bytes=N] [--timeout=2m] [files...]
Without files, scans all mise installed versions recursively and PATH directories non-recursively.
With files, inspects only those files. Never executes targets, installs or updates packages.
Exit: 0 completed (NOT safe), 1 incomplete, 2 usage error. Size limit defaults to 512MiB.
The timeout is cooperative, not a hard filesystem I/O deadline.
`
)

type Report struct {
	Notice        string    `json:"notice"`
	Inventory     Inventory `json:"inventory"`
	Findings      []Finding `json:"findings"`
	NonNative     int       `json:"non_native"`
	UnknownImages int       `json:"unknown_images"`
	Incomplete    bool      `json:"incomplete"`
}

func main() { os.Exit(runCLI(context.Background(), os.Args[1:], os.Stdout)) }

func runCLI(parent context.Context, args []string, out io.Writer) int {
	flags := flag.NewFlagSet("brotli-doctor", flag.ContinueOnError)
	flags.SetOutput(io.Discard)
	asJSON := flags.Bool("json", false, "JSON output")
	useMise := flags.Bool("mise", true, "inventory installed mise versions")
	usePATH := flags.Bool("path", true, "inventory direct PATH entries")
	maxBytes := flags.Int64("max-bytes", 512<<20, "maximum bytes per file, up to 512MiB")
	timeout := flags.Duration("timeout", 2*time.Minute, "cooperative scan deadline")
	if err := flags.Parse(args); err != nil {
		_, _ = io.WriteString(out, help)
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	if *maxBytes <= 0 || *maxBytes > 512<<20 || *timeout <= 0 || *timeout > 30*time.Minute || (flags.NArg() == 0 && !*useMise && !*usePATH) {
		_, _ = io.WriteString(out, help)
		return 2
	}
	ctx, cancel := context.WithTimeout(parent, *timeout)
	defer cancel()
	inventory := inventoryFor(ctx, flags.Args(), *useMise, *usePATH)
	report := scan(ctx, inventory, *maxBytes)
	if err := outputReport(out, report, *asJSON); err != nil {
		return 1
	}
	if report.Incomplete {
		return 1
	}
	return 0
}

func inventoryFor(ctx context.Context, files []string, useMise, usePATH bool) Inventory {
	if len(files) > 0 {
		c := collector{seen: map[string]bool{}, ctx: ctx}
		for _, file := range files {
			path, err := filepath.Abs(file)
			if err != nil {
				c.issue(file, err)
				continue
			}
			// Explicit files may be cross-built images without executable permissions.
			path, err = filepath.EvalSymlinks(path)
			if err != nil {
				c.issue(file, err)
				continue
			}
			if !c.seen[path] {
				c.seen[path] = true
				c.result.Paths = append(c.result.Paths, path)
			} else {
				c.result.Duplicates++
			}
		}
		return c.result
	}
	var roots, dirs, issues []string
	if useMise {
		data, err := miseInventory(ctx)
		if err == nil {
			roots, err = parseMise(data)
		}
		if err != nil {
			issues = append(issues, "mise inventory: "+err.Error())
		}
	}
	if usePATH {
		dirs = filepath.SplitList(os.Getenv("PATH"))
		if len(dirs) == 0 {
			issues = append(issues, "PATH is empty; no PATH coverage")
		}
	}
	result := collect(ctx, roots, dirs)
	result.Issues = append(result.Issues, issues...)
	return result
}

func scan(ctx context.Context, inventory Inventory, maxBytes int64) Report {
	report := Report{Notice: disclaimer, Inventory: inventory, Incomplete: len(inventory.Issues) > 0}
	for _, path := range inventory.Paths {
		if err := ctx.Err(); err != nil {
			report.Inventory.Issues = append(report.Inventory.Issues, err.Error()+"; remaining candidates uninspected")
			report.Incomplete = true
			break
		}
		finding, native := inspect(ctx, path, maxBytes)
		if native || len(finding.Issues) > 0 {
			report.Findings = append(report.Findings, finding)
		} else {
			report.NonNative++
		}
		if len(finding.Issues) > 0 {
			report.Incomplete = true
		}
		for _, image := range finding.Images {
			if evidenceState(image.Evidence) == "UNKNOWN" {
				report.UnknownImages++
			}
			if len(image.Issues) > 0 {
				report.Incomplete = true
			}
		}
	}
	return report
}

func outputReport(out io.Writer, report Report, asJSON bool) error {
	if asJSON {
		data, err := json.Marshal(report)
		if err != nil {
			return err
		}
		_, err = fmt.Fprintln(out, string(data))
		return err
	}
	var text strings.Builder
	fmt.Fprintln(&text, report.Notice)
	for _, issue := range report.Inventory.Issues {
		fmt.Fprintf(&text, "INCOMPLETE inventory %q\n", issue)
	}
	for _, finding := range report.Findings {
		fmt.Fprintf(&text, "FILE %q\n", finding.Path)
		for _, issue := range finding.Issues {
			fmt.Fprintf(&text, "  INCOMPLETE %q\n", issue)
		}
		for _, image := range finding.Images {
			fmt.Fprintf(&text, "  %s %q %q\n", evidenceState(image.Evidence), image.Format, image.Architecture)
			for _, e := range image.Evidence {
				fmt.Fprintf(&text, "    %s %q\n", e.Kind, e.Detail)
			}
			for _, review := range image.RuntimeReviews {
				fmt.Fprintf(&text, "    Bun candidate=%q comparison=%s binary-identity=%s patch-status=%s %s reviewed-release=%s reviewed-at=%s source=%s\n", review.CandidateVersion, review.Comparison, review.BinaryIdentity, review.PatchStatus, review.CVE, review.ReviewedRelease, review.ReviewedAt, review.Source)
			}
			for _, issue := range image.Issues {
				fmt.Fprintf(&text, "    INCOMPLETE %q\n", issue)
			}
		}
	}
	fmt.Fprintf(&text, "SUMMARY candidates=%d reports=%d non-native=%d unknown-images=%d excluded=%d duplicates=%d incomplete=%t\n", len(report.Inventory.Paths), len(report.Findings), report.NonNative, report.UnknownImages, report.Inventory.Excluded, report.Inventory.Duplicates, report.Incomplete)
	fmt.Fprintln(&text, "Next: dynamic-import -> verify resolved library/package version; c-defined-symbol -> investigate embedded C and rebuild if affected; go-module -> review recorded version/replacement; string hints/UNKNOWN -> obtain build records or SBOM. Pure implementation evidence does not exclude C code. Bun string candidates never verify binary identity or patch status: verify provenance; rebuild standalone artifacts with a reviewed fixed runtime, replace images/binaries and restart through normal deployment procedures.")
	_, err := io.WriteString(out, text.String())
	return err
}

type cappedOutput struct {
	data     []byte
	overflow bool
}

func (b *cappedOutput) Write(p []byte) (int, error) {
	if len(b.data)+len(p) > 8<<20 {
		b.overflow = true
		return 0, errors.New("mise output exceeds 8MiB")
	}
	b.data = append(b.data, p...)
	return len(p), nil
}

func miseInventory(parent context.Context) ([]byte, error) {
	ctx, cancel := context.WithTimeout(parent, 15*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "mise", "ls", "--installed", "--json")
	cmd.WaitDelay = time.Second
	var stdout cappedOutput
	cmd.Stdout = &stdout
	// Suppress arbitrary stderr, including local environment secrets.
	cmd.Stderr = io.Discard
	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("mise ls --installed --json: %w", err)
	}
	if stdout.overflow {
		return nil, errors.New("mise output exceeded limit")
	}
	return stdout.data, nil
}
