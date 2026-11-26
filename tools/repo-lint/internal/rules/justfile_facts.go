package rules

import (
	"regexp"
	"slices"
	"strings"
)

const (
	templateGate   = "templates/agent-baseline/.github/workflows/quality-gate.yaml"
	doctorScript   = "scripts/doctor.sh"
	gcStatusScript = "scripts/gc_status.sh"
)

// factFiles are the texts the recipe facts read.
type factFiles struct {
	just, template, gate, doctor, gcStatus string
}

// A recipe fact is a test that read the justfile, ported with the part of the
// file its test searched (ADR-0093). Each extraction below is named after the
// test helper it ports.

// splitBlock is the text after the first marker up to the first blank line:
// `text.split(marker, 1)[1].split("\n\n", 1)[0]`.
func splitBlock(text, marker string) string {
	_, after, ok := strings.Cut(text, marker)
	if !ok {
		return ""
	}
	before, _, _ := strings.Cut(after, "\n\n")
	return before
}

// linesAfter is the lines after the first line the header matches, up to the
// first line stop reports, and whether the header was found.
func linesAfter(text string, header *regexp.Regexp, stop func(string) bool) ([]string, bool) {
	lines := strings.Split(text, "\n")
	for i, line := range lines {
		if !header.MatchString(line) {
			continue
		}
		var body []string
		for _, next := range lines[i+1:] {
			if stop(next) {
				break
			}
			body = append(body, next)
		}
		return body, true
	}
	return nil, false
}

func indented(line string) bool {
	return strings.HasPrefix(line, " ") || strings.HasPrefix(line, "\t")
}

// atColumnZero: a line that ends a recipe, `^\S`.
func atColumnZero(line string) bool { return line != "" && !indented(line) }

// notIndented: a line that is not part of a run of indented lines.
func notIndented(line string) bool { return !indented(line) }

// shownOnly: an echo or a comment other than a shebang runs nothing.
var shownOnly = regexp.MustCompile(`^\s*(?:@?echo\s|#)`)

// gateCommands ports test_cross_platform_gates' `_recipe`: the recipe's lines
// up to the next column-0 line, echo lines and comments (not `#!`) dropped.
func gateCommands(text, name string) string {
	header := regexp.MustCompile(`^` + regexp.QuoteMeta(name) + `(?:\s[^:]*)?:(?:\s|$)`)
	lines, _ := linesAfter(text, header, atColumnZero)
	var body []string
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if shownOnly.MatchString(line) && !strings.HasPrefix(trimmed, "#!") {
			continue
		}
		body = append(body, line)
	}
	return strings.Join(body, "\n")
}

// frontendRecipe ports test_frontend_ci_conformance's `_recipe`: the run of
// indented lines below the only header of the recipe.
func frontendRecipe(text, name string) string {
	header := regexp.MustCompile(`^` + regexp.QuoteMeta(name) + `:`)
	count := 0
	for line := range strings.SplitSeq(text, "\n") {
		if header.MatchString(line) {
			count++
		}
	}
	if count != 1 {
		return ""
	}
	lines, _ := linesAfter(text, header, notIndented)
	return strings.Join(lines, "\n")
}

// bodyBelow is the recipe's lines below a header line that matches exactly,
// up to the next column-0 line.
func bodyBelow(text, headerLine string) (string, bool) {
	lines, ok := linesAfter(text, regexp.MustCompile(`^`+regexp.QuoteMeta(headerLine)+`$`), atColumnZero)
	return strings.Join(lines, "\n"), ok
}

var platforms = []string{"darwin", "linux", "win32"}

var pythonPlatform = regexp.MustCompile(`ty check --python-platform (\S+)`)

func platformsOf(body string) []string {
	var out []string
	for _, m := range pythonPlatform.FindAllStringSubmatch(body, -1) {
		out = append(out, m[1])
	}
	slices.Sort(out)
	return out
}

// justfileRecipeFacts: the recipes keep the wiring the tests that read the
// justfile held, each over the part of the file its test searched.
func justfileRecipeFacts() Rule {
	const id = "justfile-recipe-facts"
	return Rule{
		ID:  id,
		Why: "the recipes keep their wiring: secret scans, encrypted state, loopback servers, gate legs and the commands other files name",
		Inputs: []Input{
			{Path: justfilePath, Format: Text},
			{Path: templateJustfile, Format: Text},
			{Path: templateGate, Format: Text},
			{Path: doctorScript, Format: Text},
			{Path: gcStatusScript, Format: Text},
		},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: justfilePath}
			f := factFiles{}
			f.just, _ = in[justfilePath].(string)
			f.template, _ = in[templateJustfile].(string)
			f.gate, _ = in[templateGate].(string)
			f.doctor, _ = in[doctorScript].(string)
			f.gcStatus, _ = in[gcStatusScript].(string)
			for _, fact := range recipeFacts {
				fact(r, f)
			}
			return r.out
		},
	}
}

var recipeFacts = []func(*report, factFiles){
	secretScanFacts,
	ciAuditFacts,
	tailnetFacts,
	gateFacts,
	powershellLegFacts,
	goLintFacts,
	agentBumpFacts,
	templateFacts,
	jsFacts,
	gcloudFacts,
	emuFmtFacts,
	envGuardFacts,
	serverFacts,
	runnerFacts,
	maintenanceFacts,
	pathFacts,
	windowsSetupFacts,
}

// secretScanFacts: the commit-msg secret scan is installed, and the staged
// scan passes the gate's value (ADR-0093 D4 guards).
func secretScanFacts(r *report, f factFiles) {
	hooks := splitBlock(f.just, "\ninstall-hooks:")
	for _, hook := range []string{"--hook-type commit-msg", "--hook-type pre-commit"} {
		if !strings.Contains(hooks, hook) {
			r.add("install-hooks must run prek install %s: the secret scan runs there", hook)
		}
	}
	if staged := splitBlock(f.just, "\ncheck-forbidden-tokens:"); !strings.Contains(staged, "FORBIDDEN_TOKEN_GATE") {
		r.add("check-forbidden-tokens must pass FORBIDDEN_TOKEN_GATE, the value the hook runs with")
	}
}

var ciAuditBody = regexp.MustCompile(`(?ms)^ci-audit [^\n]*:\n(.*?)(?:^\S|\z)`)

// ciAuditFacts: an argument with spaces reaches the Go tool whole.
func ciAuditFacts(r *report, f factFiles) {
	start := strings.Index(f.just, "\nci-audit *args:\n")
	if start < 0 || !strings.Contains(f.just[max(strings.LastIndex(f.just[:start], "\n\n"), 0):start], "[positional-arguments]") {
		r.add("ci-audit *args must carry [positional-arguments]: {{ args }} splits an argument with spaces")
	}
	if m := ciAuditBody.FindStringSubmatch(f.just); m == nil || !strings.Contains(m[1], `args=("$@")`) {
		r.add(`ci-audit must read its arguments with args=("$@")`)
	}
}

var tailnetInit = regexp.MustCompile(`(?m)^tailnet-init.*\n(?:[ \t]+.*\n)*`)

// tailnetFacts: the tailnet state is encrypted with its own passphrase, and
// the backend is spelled out in main.tf.
func tailnetFacts(r *report, f factFiles) {
	for _, s := range []string{"_tailnet-encryption", "tailnet.passphrase"} {
		if !strings.Contains(f.just, s) {
			r.add("the tailnet recipes must build TF_ENCRYPTION from the local passphrase file: %s is missing", s)
		}
	}
	if init := tailnetInit.FindString(f.just); init == "" || strings.Contains(init, "backend-config") {
		r.add("tailnet-init must exist and take no backend-config; the backend is spelled out in main.tf")
	}
}

var checkTyLine = regexp.MustCompile(`(?m)^\s+@?just check-ty\s*$`)

// gateFacts: check runs its three parts, Go last; ty runs once per platform.
func gateFacts(r *report, f factFiles) {
	check := gateCommands(f.just, "check")
	var commands []string
	for line := range strings.SplitSeq(check, "\n") {
		if line != "" {
			commands = append(commands, strings.TrimLeft(strings.TrimSpace(line), "@"))
		}
	}
	if want := []string{"just check-except-go", "just go-lint", "just go-test"}; !slices.Equal(commands, want) {
		r.add("recipe check must run exactly %q, Go last; it runs %q", want, commands)
	}
	exceptGo := gateCommands(f.just, "check-except-go")
	if !checkTyLine.MatchString(exceptGo) || strings.Contains(exceptGo, "ty check") {
		r.add("check-except-go must run ty only through `just check-ty`, never ty check itself")
	}
	checkTy := gateCommands(f.just, "check-ty")
	if got := platformsOf(checkTy); !slices.Equal(got, platforms) {
		r.add("check-ty must run ty check once per platform %v; it runs %v", platforms, got)
	}
}

var (
	powershellAttrs = regexp.MustCompile(`(?m)((?:^\[[^\]]*\]\n)+)test-windows-powershell:\n`)
	powershellRun   = "export DOTFILES_TEST_PWSH=powershell.exe PODMAN_GC_REQUIRE_PWSH=1"
	powershellTests = []string{
		"test_podman_gc_simulation.py -k powershell", "test_runner_gc.py",
		"test_bootstrap_ps1.py", "test_podman_provisioning_ps1.py",
	}
)

// powershellLegFacts: the Windows PowerShell 5.1 leg checks the runtime, then
// runs the scripts' tests under it.
func powershellLegFacts(r *report, f factFiles) {
	attrs := powershellAttrs.FindStringSubmatch(f.just)
	if attrs == nil || !strings.Contains(attrs[1], "[group('test')]\n") || !strings.Contains(attrs[1], "[windows]\n") {
		r.add("test-windows-powershell must be a [windows] recipe in [group('test')]")
	}
	body := gateCommands(f.just, "test-windows-powershell")
	if !strings.Contains(body, `"5.1."*" Desktop")`) {
		r.add(`test-windows-powershell must check for "5.1."*" Desktop"`)
	}
	run := strings.Index(body, powershellRun)
	if esac := strings.Index(body, "esac"); run < 0 || esac < 0 || esac > run {
		r.add("test-windows-powershell must export %q after the runtime check's esac", powershellRun)
		return
	}
	for _, name := range powershellTests {
		if !strings.Contains(body[run:], "tests/unit/"+name) {
			r.add("test-windows-powershell must run tests/unit/%s", name)
		}
	}
}

var (
	goosLoop   = regexp.MustCompile(`for goos in ([^;\n]+); do`)
	goosLint   = regexp.MustCompile(`GOOS="\$goos" [^\n]*golangci-lint run `)
	goosNeeded = []string{"darwin", "linux", "windows"}
)

// goLintFacts: golangci-lint runs once per GOOS the binaries ship to, and
// formats once.
func goLintFacts(r *report, f factFiles) {
	body := gateCommands(f.just, "go-lint")
	var gooses []string
	if m := goosLoop.FindStringSubmatch(body); m != nil {
		gooses = strings.Fields(m[1])
		slices.Sort(gooses)
		gooses = slices.Compact(gooses)
	}
	if !slices.Equal(gooses, goosNeeded) || !goosLint.MatchString(body) {
		r.add(`go-lint must run GOOS="$goos" golangci-lint run for each GOOS of %v`, goosNeeded)
	}
	if n := strings.Count(body, "golangci-lint fmt "); n != 1 {
		r.add("go-lint must run golangci-lint fmt once per module, not %d times", n)
	}
}

// agentBumpFacts: agent-bump runs the Go tool against this checkout and
// forwards its arguments.
func agentBumpFacts(r *report, f factFiles) {
	body := splitBlock(f.just, "agent-bump *args:\n")
	for _, s := range []string{"go -C tools/agent-bump run . --root", "{{ args }}"} {
		if !strings.Contains(body, s) {
			r.add("agent-bump must run the Go tool on this checkout with its arguments: %s is missing", s)
		}
	}
}

var templateCheck = regexp.MustCompile(`^check\s*:([^=].*|)$`)

// templateFacts: a scaffolded repository's strict gate never writes and
// type-checks every OS, and its CI runs it.
func templateFacts(r *report, f factFiles) {
	lint := gateCommands(f.template, "lint")
	if got := platformsOf(lint); !slices.Equal(got, platforms) {
		r.addAt(templateJustfile, "the template's lint must run ty check once per platform %v; it runs %v", platforms, got)
	}
	for i := strings.Index(lint, "ty check"); i >= 0; {
		if !strings.HasPrefix(lint[i+len("ty check"):], " --python-platform") {
			r.addAt(templateJustfile, "the template's lint runs ty check without --python-platform")
			break
		}
		next := strings.Index(lint[i+1:], "ty check")
		if next < 0 {
			break
		}
		i += 1 + next
	}
	var deps []string
	for line := range strings.SplitSeq(f.template, "\n") {
		if m := templateCheck.FindStringSubmatch(line); m != nil {
			before, _, _ := strings.Cut(m[1], "#")
			deps = strings.Fields(before)
			break
		}
	}
	if slices.Contains(deps, "fmt") {
		r.addAt(templateJustfile, "the template's check must not depend on fmt: the strict gate never writes")
	}
	for _, need := range []string{"lint", "semgrep", "test"} {
		if !slices.Contains(deps, need) {
			r.addAt(templateJustfile, "the template's check must depend on %s", need)
		}
	}
	const noFix = "uv run --locked --only-group lint ruff check --no-fix --no-fix-only ."
	lines, _ := linesAfter(f.template, regexp.MustCompile(`^lint\s*:`), atColumnZero)
	if !slices.ContainsFunc(lines, func(l string) bool { return strings.TrimSpace(l) == noFix }) {
		r.addAt(templateJustfile, "the template's lint must run %q", noFix)
	}
	if !regexp.MustCompile(`(?m)^\s+run: just check\s*$`).MatchString(f.gate) {
		r.addAt(templateGate, "the template's CI must run `just check`")
	}
}

var (
	oxlintTracked = regexp.MustCompile(`git ls-files -z -- \{\{ JS_TRACKED \}\} \| xargs -0 -r bunx --no-install oxlint\s*$`)
	jsFilesLine   = regexp.MustCompile(`(?m)^JS_FILES := "(.+)"$`)
	jsTrackedLine = `JS_TRACKED := replace(JS_FILES, " ':!vendor/**'", "")`
	jsFilesWant   = []string{
		"'*.ts'", "'*.tsx'", "'*.js'", "'*.jsx'", "'*.mjs'", "'*.cjs'", "'*.mts'", "'*.cts'",
		"':(top,exclude).semgrep/**'", "':!vendor/**'",
	}
)

// jsFacts: oxlint gets the tracked files only, from one list, and the JS
// suite runs whole.
func jsFacts(r *report, f factFiles) {
	lint := frontendRecipe(f.just, "js-lint")
	if !oxlintTracked.MatchString(strings.ReplaceAll(lint, "{{ BUN }}x", "bunx")) {
		r.add("js-lint must hand oxlint the tracked files only: git ls-files -z -- {{ JS_TRACKED }} | xargs -0 -r bunx --no-install oxlint")
	}
	if !strings.Contains(f.just, jsTrackedLine) {
		r.add("the justfile must define %s", jsTrackedLine)
	}
	if m := jsFilesLine.FindAllStringSubmatch(f.just, -1); len(m) != 1 || !slices.Equal(strings.Fields(m[0][1]), jsFilesWant) {
		r.add("JS_FILES must be exactly %v", jsFilesWant)
	}
	test := frontendRecipe(f.just, "js-test")
	if !strings.Contains(test, "test ./tests/unit/") {
		r.add("js-test must run the whole suite, test ./tests/unit/")
	}
	for _, flag := range []string{"--changed", "--shard"} {
		if strings.Contains(test, flag) {
			r.add("js-test must not run with %s", flag)
		}
	}
}

// gcloudFilter is the "installed" filter, as the justfile string escapes it.
const gcloudFilter = `state.name=\"Installed\" OR state.name=\"Update Available\"`

// gcloudFacts: dump and restore share one definition of "installed".
func gcloudFacts(r *report, f factFiles) {
	if !strings.Contains(f.just, "GCLOUD_INSTALLED := ") || !strings.Contains(f.just, gcloudFilter) {
		r.add("the justfile must define GCLOUD_INSTALLED with the filter %s", gcloudFilter)
	}
	for _, name := range []string{"dump:", "add-gcloud host"} {
		start := strings.Index(f.just, "\n"+name)
		end := -1
		if start >= 0 {
			end = strings.Index(f.just[start+1:], "\n\n")
		}
		if start < 0 || end < 0 || !strings.Contains(f.just[start:start+1+end], "{{ GCLOUD_INSTALLED }}") {
			r.add("recipe %s must list with {{ GCLOUD_INSTALLED }}", strings.TrimSuffix(name, ":"))
		}
	}
	for _, old := range []string{"state.name=Installed'", "state.name:("} {
		if strings.Contains(f.just, old) {
			r.add("the justfile holds the old gcloud filter %s", old)
		}
	}
}

var goFmtWord = regexp.MustCompile(`\bgo fmt\b`)

// emuFmtFacts: the emulator's Go is formatted by golangci-lint (gofumpt).
func emuFmtFacts(r *report, f factFiles) {
	lines, ok := linesAfter(f.just, regexp.MustCompile(`^emu-fmt:\s*$`), func(l string) bool {
		return atColumnZero(l) && !strings.HasPrefix(l, "#")
	})
	body := strings.Join(lines, "\n")
	if !ok || !strings.Contains(body, "golangci-lint fmt") {
		r.add("emu-fmt must format the Go CLIs with golangci-lint fmt")
	}
	if goFmtWord.MatchString(body) {
		r.add("emu-fmt must not use go fmt; golangci-lint fmt (gofumpt) is the gate")
	}
}

var doubleDollarGuard = regexp.MustCompile(`\$\$\{[A-Z_][A-Z0-9_]*:\?[^}]*\}`)

// envGuardFacts: `$${VAR:?msg}` expands to <pid>{VAR:?msg} in a shebang
// recipe, so the guard never fires.
func envGuardFacts(r *report, f factFiles) {
	if m := doubleDollarGuard.FindAllString(f.just, -1); m != nil {
		r.add("broken $${VAR:?msg} guards %q: write ${VAR:?msg}", m)
	}
}

var (
	bindLoopback = regexp.MustCompile(`(?:-b|--bind)\s+127\.0\.0\.1`)
	serverHost   = regexp.MustCompile(`-host\s+(\S+)`)
	serverDir    = regexp.MustCompile(`-dir\s+(\{\{.*?\}\}|\S+)`)
	whitespace   = regexp.MustCompile(`\s`)
)

// serverFacts: the checkout holds private keys and certificates, so a local
// server listens on loopback and serves only what Pages publishes (D4).
func serverFacts(r *report, f factFiles) {
	var servers []string
	for line := range strings.SplitSeq(f.just, "\n") {
		if strings.Contains(line, "http.server") || strings.Contains(line, "simple-server") && strings.Contains(" "+line, " go run ") {
			servers = append(servers, strings.TrimSpace(line))
		}
	}
	if !slices.ContainsFunc(servers, func(l string) bool {
		return strings.Contains(l, "site-serve") || strings.Contains(l, "-host 127.0.0.1")
	}) {
		r.add("no local server binds -host 127.0.0.1")
	}
	for _, line := range servers {
		if strings.Contains(line, "http.server") && !bindLoopback.MatchString(line) {
			r.add("a local server must bind 127.0.0.1: %s", line)
		}
		if m := serverHost.FindStringSubmatch(line); m != nil && m[1] != "127.0.0.1" && m[1] != "localhost" {
			r.add("a local server must listen on loopback: %s", line)
		}
		if m := serverDir.FindStringSubmatch(line); m != nil && slices.Contains([]string{".", "./", "{{justfile_directory()}}"}, whitespace.ReplaceAllString(m[1], "")) {
			r.add("a local server must not serve the checkout: %s", line)
		}
	}
}

var (
	statusWired    = regexp.MustCompile(`(?m)^status:\n\s+bash scripts/gc_status\.sh`)
	runHiddenBuild = regexp.MustCompile(`(?ms)^run-hidden-build:\n(.*?)(?:^\S|\z)`)
)

// runnerFacts: status validates the runner hook rather than its presence,
// and run-hidden is a GUI-subsystem binary that opens no window.
func runnerFacts(r *report, f factFiles) {
	for _, s := range []string{"is not a valid path to a script", ".ps1", ".sh"} {
		if !strings.Contains(f.gcStatus, s) {
			r.addAt(gcStatusScript, "status must check the runner hook (%s): the job log holds the only record of a rejection", s)
		}
	}
	if !statusWired.MatchString(f.just) {
		r.add("`just status` must run bash scripts/gc_status.sh")
	}
	m := runHiddenBuild.FindStringSubmatch(f.just)
	for _, s := range []string{"tools/run-hidden", "-H=windowsgui", "output/run-hidden/run-hidden.exe"} {
		if m == nil || !strings.Contains(m[1], s) {
			r.add("run-hidden-build must build a windowsgui binary: %s is missing", s)
		}
	}
}

var (
	submoduleGuard = regexp.MustCompile(`git\s+-c\s+submodule\.recurse=false\s+submodule\s+update\s+--remote`)
	telDown        = regexp.MustCompile(`(?m)^tel-down:\n((?:    .*\n)+)`)
)

// maintenanceFacts: the update recipes run on the baseline git, keep nested
// submodules pinned, remove an older telemetry stack, and update Pi.
func maintenanceFacts(r *report, f factFiles) {
	lines, _ := linesAfter(f.just, regexp.MustCompile(`^update-all-submodules[^:\n]*:`), atColumnZero)
	body := strings.Join(lines, "\n")
	if strings.Contains(body, "--no-recurse-submodules") || !submoduleGuard.MatchString(body) {
		r.add("update-all-submodules must use git -c submodule.recurse=false submodule update --remote (git 2.43 lacks --no-recurse-submodules)")
	}
	if m := telDown.FindStringSubmatch(f.just); m == nil || !strings.Contains(m[1], "{{ PODMAN_COMPOSE }} down --remove-orphans") {
		r.add("tel-down must run {{ PODMAN_COMPOSE }} down --remove-orphans")
	}
	for _, name := range []string{"update-all", "update-all-safe"} {
		body, _ := bodyBelow(f.just, name+":")
		step := ""
		for line := range strings.SplitSeq(body, "\n") {
			if strings.Contains(line, "pi update --extensions") {
				step = line
				break
			}
		}
		if !strings.Contains(body, "command -v pi") || !strings.Contains(step, "pi update --extensions ||") {
			r.add("%s must run pi update --extensions || ..., only when command -v pi finds it", name)
		}
	}
}

var (
	validateDuplicates = regexp.MustCompile(`(?ms)^validate-path-duplicates:\n(.*?)^\S`)
	driveMount         = regexp.MustCompile(`/mnt/\[a-zA-Z\]`)
)

// pathFacts: the PATH scan skips Windows drive mounts, and doctor runs the
// contamination check.
func pathFacts(r *report, f factFiles) {
	if m := validateDuplicates.FindStringSubmatch(f.just); m == nil || !driveMount.MatchString(m[1]) {
		r.add("validate-path-duplicates must skip /mnt/<drive> PATH entries")
	}
	if !strings.Contains(f.just, "\nvalidate-path-windows:") {
		r.add("recipe validate-path-windows must exist")
	}
	if !strings.Contains(f.doctor, "just validate-path-windows") {
		r.addAt(doctorScript, "doctor must run `just validate-path-windows`")
	}
}

var (
	addScoopBody    = regexp.MustCompile(`(?ms)^add-scoop[^:\n]*:.*?\n(.*?)(?:^[A-Za-z_][\w-]*[^:\n]*:|\z)`)
	unameCase       = regexp.MustCompile(`case\s+"\$\(uname\s+-s\)"\s+in`)
	wslConfRecipe   = regexp.MustCompile(`(?m)^wsl-conf:`)
	wslconfigRecipe = regexp.MustCompile(`(?m)^wslconfig:`)
)

// windowsSetupFacts: add-scoop restores the host's record with scoop import
// and needs no jq; the WSL advisors surface their templates.
func windowsSetupFacts(r *report, f factFiles) {
	m := addScoopBody.FindStringSubmatch(f.just)
	body := ""
	if m != nil {
		body = m[1]
	}
	for _, s := range []string{"scoop.json", "resolve-restore", "scoop import", "MINGW"} {
		if !strings.Contains(body, s) {
			r.add("add-scoop must restore dump/<host>/scoop.json with scoop import, Windows-guarded: %s is missing", s)
		}
	}
	if !unameCase.MatchString(body) {
		r.add(`add-scoop must dispatch on case "$(uname -s)" in`)
	}
	if strings.Contains(body, "jq") {
		r.add("add-scoop must not depend on jq: it is one of the apps being restored")
	}
	if !wslConfRecipe.MatchString(f.just) || !strings.Contains(f.just, "config/wsl/wsl.conf") {
		r.add("recipe wsl-conf must surface config/wsl/wsl.conf")
	}
	if !wslconfigRecipe.MatchString(f.just) || !strings.Contains(f.just, "config/wsl/wslconfig") && !strings.Contains(f.just, "wslconfig_conf.sh") {
		r.add("recipe wslconfig must surface config/wsl/wslconfig or run wslconfig_conf.sh")
	}
}
