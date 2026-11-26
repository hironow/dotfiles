package rules

import "testing"

const factsJustfile = `JS_FILES := "'*.ts' '*.tsx' '*.js' '*.jsx' '*.mjs' '*.cjs' '*.mts' '*.cts' ':(top,exclude).semgrep/**' ':!vendor/**'"
JS_TRACKED := replace(JS_FILES, " ':!vendor/**'", "")
GCLOUD_INSTALLED := "gcloud components list --filter='state.name=\"Installed\" OR state.name=\"Update Available\"' --format='value(id)'"

install-hooks:
    prek install --hook-type pre-commit --hook-type commit-msg

check-forbidden-tokens:
    python3 scripts/check_forbidden_tokens.py {{ FORBIDDEN_TOKEN_GATE }} --staged

[positional-arguments]
ci-audit *args:
    args=("$@")
    go -C tools/ci-audit run . "${args[@]}"

_tailnet-encryption:
    cat tailnet.passphrase

tailnet-init:
    tofu init

check:
    @just check-except-go
    @echo 'Go (golangci-lint per GOOS)...'
    just go-lint
    just go-test

check-except-go:
    @echo 'Python (ty check per platform)...'
    @just check-ty

check-ty:
    ty check --python-platform win32
    ty check --python-platform linux
    ty check --python-platform darwin

[group('test')]
[windows]
test-windows-powershell:
    case "$(x)" in "5.1."*" Desktop") ;; *) exit 1 ;; esac
    export DOTFILES_TEST_PWSH=powershell.exe PODMAN_GC_REQUIRE_PWSH=1
    uv run pytest tests/unit/test_podman_gc_simulation.py -k powershell tests/unit/test_runner_gc.py tests/unit/test_bootstrap_ps1.py tests/unit/test_podman_provisioning_ps1.py

go-lint:
    for goos in windows linux darwin; do
      (GOOS="$goos" golangci-lint run ./...)
    done
    echo "golangci-lint fmt --diff"
    (golangci-lint fmt --diff ./...)

agent-bump *args:
    go -C tools/agent-bump run . --root {{ justfile_directory() }} {{ args }}

js-lint:
    git ls-files -z -- {{ JS_TRACKED }} | xargs -0 -r {{ BUN }}x --no-install oxlint

js-test:
    {{ BUN }} test ./tests/unit/

dump:
    {{ GCLOUD_INSTALLED }} > listing

add-gcloud host="":
    installed=$({{ GCLOUD_INSTALLED }})

emu-fmt:
    golangci-lint fmt ./...
# formats with gofumpt

site-serve:
    python3 -m http.server 8000 -b 127.0.0.1 -d site/

pages-serve:
    go run ./tools/simple-server -host 127.0.0.1 -dir site

status:
    bash scripts/gc_status.sh

run-hidden-build:
    go build -ldflags=-H=windowsgui -o output/run-hidden/run-hidden.exe ./tools/run-hidden

update-all-submodules:
    git -c submodule.recurse=false submodule update --remote --force --checkout

tel-down:
    cd telemetry && {{ PODMAN_COMPOSE }} down --remove-orphans

update-all:
    if command -v pi >/dev/null; then pi update --extensions || echo warn; fi

update-all-safe:
    if command -v pi >/dev/null; then pi update --extensions || echo warn; fi

validate-path-duplicates:
    case "$dir" in /mnt/[a-zA-Z]|/mnt/[a-zA-Z]/*) continue ;; esac

validate-path-windows:
    echo check

[windows]
add-scoop host="":
    case "$(uname -s)" in MINGW*) ;; esac
    host="$(bash scripts/dump_host.sh resolve-restore {{ quote(host) }})"
    scoop import "dump/$host/scoop.json"

wsl-conf:
    cat config/wsl/wsl.conf

wslconfig:
    bash scripts/wslconfig_conf.sh
`

const factsTemplate = `check: lint semgrep test
    @echo ok

lint:
    uv run --locked --only-group lint ruff check --no-fix --no-fix-only .
    uv run ty check --python-platform win32
    uv run ty check --python-platform linux
    uv run ty check --python-platform darwin
`

func TestJustfileRecipeFacts(t *testing.T) {
	base := func() Inputs {
		return Inputs{
			justfilePath:     factsJustfile,
			templateJustfile: factsTemplate,
			templateGate:     "jobs:\n  gate:\n    steps:\n      - name: gate\n        run: just check\n",
			doctorScript:     "just validate-path-windows\n",
			gcStatusScript:   "grep 'is not a valid path to a script'\ncase x in *.ps1|*.sh) ;; esac\n",
		}
	}
	j, tpl := justfilePath, templateJustfile
	runCases(t, justfileRecipeFacts(), base, []ruleCase{
		{"install-hooks skips the commit-msg hook", edit(j, " --hook-type commit-msg", ""), "commit-msg"},
		{"install-hooks skips the pre-commit hook", edit(j, "--hook-type pre-commit ", ""), "pre-commit"},
		{"the staged scan loses the gate", edit(j, "{{ FORBIDDEN_TOKEN_GATE }} --staged", "--staged"), "FORBIDDEN_TOKEN_GATE"},
		{"ci-audit splits its arguments", edit(j, "[positional-arguments]\nci-audit", "ci-audit"), "positional-arguments"},
		{"ci-audit reads its arguments otherwise", edit(j, `args=("$@")`, "args={{ args }}"), `args=("$@")`},
		{"the passphrase recipe is gone", edit(j, "_tailnet-encryption:", "_tailnet-key:"), "_tailnet-encryption"},
		{"the passphrase file is gone", edit(j, "cat tailnet.passphrase", "cat key"), "tailnet.passphrase"},
		{"tailnet-init takes a backend config", edit(j, "    tofu init\n", "    tofu init -backend-config=backend.hcl\n"), "backend-config"},
		{"check adds a leg", edit(j, "    just go-test\n", "    just go-test\n    just docs\n"), "check"},
		{"check runs Go first", edit(j, "    @just check-except-go\n    @echo 'Go (golangci-lint per GOOS)...'\n    just go-lint\n", "    just go-lint\n    @just check-except-go\n"), "check"},
		{"check-except-go skips check-ty", edit(j, "    @just check-ty\n", "    @echo skip\n"), "check-ty"},
		{"check-except-go runs ty itself", edit(j, "    @just check-ty\n", "    @just check-ty\n    ty check\n"), "ty check"},
		{"check-ty drops a platform", edit(j, "    ty check --python-platform darwin\n", ""), "check-ty"},
		{"the 5.1 leg leaves group test", edit(j, "[group('test')]\n[windows]\ntest-windows-powershell", "[group('lint')]\n[windows]\ntest-windows-powershell"), "test-windows-powershell"},
		{"the 5.1 leg leaves Windows", edit(j, "[group('test')]\n[windows]\ntest-windows-powershell", "[group('test')]\ntest-windows-powershell"), "test-windows-powershell"},
		{"the 5.1 leg checks no runtime", edit(j, `"5.1."*" Desktop")`, `"5."*)`), "5.1"},
		{"the 5.1 leg exports before the check", edit(j, "    case \"$(x)\" in \"5.1.\"*\" Desktop\") ;; *) exit 1 ;; esac\n    export DOTFILES_TEST_PWSH=powershell.exe PODMAN_GC_REQUIRE_PWSH=1\n", "    export DOTFILES_TEST_PWSH=powershell.exe PODMAN_GC_REQUIRE_PWSH=1\n    case \"$(x)\" in \"5.1.\"*\" Desktop\") ;; *) exit 1 ;; esac\n"), "esac"},
		{"the 5.1 leg drops a suite", edit(j, " tests/unit/test_bootstrap_ps1.py", ""), "test_bootstrap_ps1.py"},
		{"go-lint drops a GOOS", edit(j, "for goos in windows linux darwin", "for goos in linux darwin"), "GOOS"},
		{"go-lint lints without GOOS", edit(j, `(GOOS="$goos" golangci-lint run ./...)`, "(golangci-lint run ./...)"), "GOOS"},
		{"go-lint formats per GOOS", edit(j, `(GOOS="$goos" golangci-lint run ./...)`, `(GOOS="$goos" golangci-lint run ./... && golangci-lint fmt ./...)`), "golangci-lint fmt"},
		{"agent-bump runs elsewhere", edit(j, "go -C tools/agent-bump run . --root", "go run ./tools/agent-bump"), "agent-bump"},
		{"agent-bump drops the arguments", edit(j, " {{ args }}\n\njs-lint", "\n\njs-lint"), "{{ args }}"},
		{"oxlint walks the disk", edit(j, "git ls-files -z -- {{ JS_TRACKED }} | xargs -0 -r {{ BUN }}x --no-install oxlint", "{{ BUN }}x --no-install oxlint ."), "oxlint"},
		{"JS_TRACKED is spelled out", edit(j, `JS_TRACKED := replace(JS_FILES, " ':!vendor/**'", "")`, `JS_TRACKED := "'*.ts'"`), "JS_TRACKED"},
		{"JS_FILES drops an extension", edit(j, " '*.mts'", ""), "JS_FILES"},
		{"the JS suite runs a shard", edit(j, "test ./tests/unit/", "test --shard 1/2 ./tests/unit/"), "--shard"},
		{"the JS suite runs changed files only", edit(j, "test ./tests/unit/", "test --changed ./tests/unit/"), "--changed"},
		{"the gcloud filter is not shared", edit(j, "GCLOUD_INSTALLED := ", "GCLOUD_LIST := "), "GCLOUD_INSTALLED"},
		{"the gcloud filter narrows", edit(j, ` OR state.name=\"Update Available\"`, ""), "filter"},
		{"dump spells its own filter", edit(j, "    {{ GCLOUD_INSTALLED }} > listing", "    gcloud components list > listing"), "dump"},
		{"restore spells its own filter", edit(j, "installed=$({{ GCLOUD_INSTALLED }})", "installed=$(gcloud components list)"), "add-gcloud"},
		{"the old narrow filter returns", edit(j, "    installed=$({{ GCLOUD_INSTALLED }})\n", "    installed=$({{ GCLOUD_INSTALLED }})\n    # was --filter='state.name=Installed'\n"), "state.name=Installed'"},
		{"emu-fmt uses go fmt", edit(j, "    golangci-lint fmt ./...\n# formats", "    go fmt ./...\n# formats"), "emu-fmt"},
		{"a comment after emu-fmt names go fmt", edit(j, "# formats with gofumpt", "# not go fmt"), "go fmt"},
		{"a $$ guard", edit(j, "    tofu init\n", "    : \"$${TF_TOKEN:?set it}\"\n    tofu init\n"), "$${"},
		{"a server binds everywhere", edit(j, "-b 127.0.0.1 -d site/", "-b 0.0.0.0 -d site/"), "http.server"},
		{"a server serves the checkout", edit(j, "-dir site", "-dir ."), "-dir"},
		{"a server listens on every host", edit(j, "-host 127.0.0.1", "-host 0.0.0.0"), "-host"},
		{"status stops reading job logs", edit(gcStatusScript, "is not a valid path to a script", "rejected"), "is not a valid path to a script"},
		{"status stops checking the extension", edit(gcStatusScript, "*.ps1|*.sh", "*"), ".ps1"},
		{"status runs something else", edit(j, "bash scripts/gc_status.sh", "bash scripts/status.sh"), "gc_status.sh"},
		{"run-hidden gets a console", edit(j, "-ldflags=-H=windowsgui ", ""), "windowsgui"},
		{"submodules use git 2.44's flag", edit(j, "git -c submodule.recurse=false submodule update --remote", "git submodule update --no-recurse-submodules --remote"), "submodule"},
		{"tel-down leaves the old stack", edit(j, "down --remove-orphans", "down"), "--remove-orphans"},
		{"the template's check formats", edit(tpl, "check: lint semgrep test", "check: fmt lint semgrep test"), "fmt"},
		{"the template's check skips semgrep", edit(tpl, "check: lint semgrep test", "check: lint test"), "semgrep"},
		{"the template's lint fixes", edit(tpl, "ruff check --no-fix --no-fix-only .", "ruff check --fix ."), "--no-fix"},
		{"a lint variable is not the lint recipe", func(in Inputs) {
			edit(tpl, "check: lint semgrep test", "lint := \"\"\"\n    uv run --locked --only-group lint ruff check --no-fix --no-fix-only .\n\"\"\"\n\ncheck: lint semgrep test")(in)
			edit(tpl, "ruff check --no-fix --no-fix-only .\n    uv run ty", "ruff check --fix .\n    uv run ty")(in)
		}, "--no-fix"},
		{"the template's lint checks one OS", edit(tpl, "    uv run ty check --python-platform darwin\n", "    uv run ty check\n"), "ty check"},
		{"the template's CI skips the gate", edit(templateGate, "run: just check", "run: just lint"), "just check"},
		{"update-all fails without Pi", edit(j, "update-all:\n    if command -v pi >/dev/null; then pi update --extensions || echo warn; fi", "update-all:\n    pi update --extensions || echo warn"), "command -v pi"},
		{"update-all-safe stops on a Pi failure", edit(j, "update-all-safe:\n    if command -v pi >/dev/null; then pi update --extensions || echo warn; fi", "update-all-safe:\n    if command -v pi >/dev/null; then pi update --extensions; fi"), "pi update --extensions ||"},
		{"the PATH scan globs drive mounts", edit(j, "/mnt/[a-zA-Z]|/mnt/[a-zA-Z]/*", "/nothing"), "/mnt"},
		{"doctor skips the contamination check", edit(doctorScript, "just validate-path-windows", "true"), "validate-path-windows"},
		{"the contamination check is gone", edit(j, "validate-path-windows:", "validate-path:"), "validate-path-windows"},
		{"add-scoop restores otherwise", edit(j, `scoop import "dump/$host/scoop.json"`, `scoop install git`), "scoop import"},
		{"add-scoop parses with jq", edit(j, `scoop import "dump/$host/scoop.json"`, `jq -r '.apps[].Name' "dump/$host/scoop.json" | xargs scoop install`), "jq"},
		{"add-scoop runs everywhere", edit(j, "    case \"$(uname -s)\" in MINGW*) ;; esac\n", ""), "uname"},
		{"wsl-conf is gone", edit(j, "wsl-conf:", "wsl-config:"), "wsl-conf"},
		{"wslconfig surfaces nothing", edit(j, "bash scripts/wslconfig_conf.sh", "echo nothing"), "wslconfig"},
	})
}
