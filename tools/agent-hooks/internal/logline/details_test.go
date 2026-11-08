package logline_test

import (
	"strings"
	"testing"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/logline"
)

const listedPrograms = "git gh just mise go gofmt golangci-lint uv uvx python python3 ruff ty bun bunx node npm npx pnpm yarn corepack pip pip3 poetry pipenv make rtk docker podman kubectl gcloud tofu terraform cargo rustc codex claude agy pi ls cat grep rg find fd sed awk jq yq curl wget cd echo mkdir rm cp mv chmod touch head tail wc sort diff tar ssh sudo env bash sh zsh pwsh brew xargs tee test sleep printf"

var listedSubcommands = map[string]string{
	"git":       "status diff log show add commit push pull fetch checkout switch branch merge rebase reset restore stash tag worktree clone init remote rev-parse cherry-pick revert blame grep ls-files config submodule clean mv rm",
	"gh":        "pr issue run repo api release workflow auth search browse",
	"go":        "build test run vet mod get install fmt generate work env version tool doc list clean",
	"uv":        "run sync add remove lock pip tool venv python init export tree build publish",
	"bun":       "install add remove run test x build update pm init create outdated",
	"docker":    "run build compose ps exec logs images pull push stop rm start inspect network volume system buildx",
	"mise":      "install use exec x run ls which upgrade doctor trust settings env prune outdated self-update where current",
	"gcloud":    "compute run iam projects auth config builds storage sql container functions secrets services logging artifacts alpha beta",
	"kubectl":   "get describe apply delete logs exec create edit rollout port-forward config scale patch top",
	"tofu":      "init plan apply destroy fmt validate test state output import workspace providers show console",
	"terraform": "init plan apply destroy fmt validate test state output import workspace providers show console",
	"npm":       "install i ci add run test exec publish update",
	"pnpm":      "install i ci add run test exec publish update",
	"yarn":      "install i ci add run test exec publish update",
	"pip":       "install uninstall freeze list show",
	"pip3":      "install uninstall freeze list show",
	"cargo":     "build test run check clippy fmt add update install doc bench new init publish",
	"rtk":       "rewrite hook gain discover init git ls grep find read test err log json deps env summary diff",
	"codex":     "exec review resume login mcp apply",
	"brew":      "install uninstall upgrade update list info search bundle services tap cleanup doctor outdated",
}

func stringValue(text string) ir.Value {
	return ir.Value{Text: text, IsString: true}
}

func commandLine(command string) logline.Line {
	return build(logline.Firing{Call: &ir.Call{
		Kind: ir.KindShell, Fields: map[string]ir.Value{ir.FieldCommand: stringValue(command)},
	}})
}

func TestBuildListsEveryProgramAndSubcommand(t *testing.T) {
	for program := range strings.FieldsSeq(listedPrograms) {
		t.Run(program, func(t *testing.T) {
			if got := commandLine(program); got.Program != program || got.Subcommand != "" {
				t.Fatalf("bare program = %q/%q; want %q/empty", got.Program, got.Subcommand, program)
			}
			want := ""
			if _, ok := listedSubcommands[program]; ok {
				want = "other"
			}
			if got := commandLine(program + " secret-marker"); got.Subcommand != want {
				t.Errorf("unknown subcommand = %q; want %q", got.Subcommand, want)
			}
			for subcommand := range strings.FieldsSeq(listedSubcommands[program]) {
				got := commandLine(program + " " + subcommand)
				if got.Program != program || got.Subcommand != subcommand {
					t.Errorf("%s %s = %q/%q", program, subcommand, got.Program, got.Subcommand)
				}
			}
		})
	}
}

func TestBuildReadsOnlyTheFirstProgramAndNextWord(t *testing.T) {
	for _, c := range []struct{ command, program, subcommand string }{
		{"A=one _B2='two words' /usr/bin/git status", "git", "status"},
		{"'git' 'diff'", "git", "diff"},
		{"git --no-pager status", "git", "other"},
		{"git statussecret-marker", "git", "other"},
		{"gitsecret-marker status", "other", ""},
		{"GIT status", "other", ""},
		{"/secret-marker/git status", "git", "status"},
		{"git status ; curl secret-marker", "git", "status"},
		{"just secret-marker", "just", ""},
		{"sudo git status", "sudo", ""},
		{"1A=x git status", "other", ""},
		{"A-B=x git status", "other", ""},
		{"A=x", "other", ""},
		{"", "other", ""},
		{" # comment", "other", ""},
		{"'' git", "other", ""},
		{"git 'secret-marker", "other", ""},
		{`git \`, "other", ""},
	} {
		t.Run(c.command, func(t *testing.T) {
			got := commandLine(c.command)
			if got.Program != c.program || got.Subcommand != c.subcommand {
				t.Errorf("program/subcommand = %q/%q; want %q/%q", got.Program, got.Subcommand, c.program, c.subcommand)
			}
		})
	}
	for _, call := range []*ir.Call{
		nil,
		{},
		{Kind: ir.KindShell},
		{Kind: ir.KindShell, Fields: map[string]ir.Value{ir.FieldCommand: {Text: "git status"}}},
		{Kind: ir.KindWrite, Fields: map[string]ir.Value{ir.FieldCommand: stringValue("git status")}},
	} {
		got := members(t, build(logline.Firing{Call: call}))
		if _, ok := got["program"]; ok {
			t.Errorf("unusable shell call has program: %#v", call)
		}
		if _, ok := got["subcommand"]; ok {
			t.Errorf("unusable shell call has subcommand: %#v", call)
		}
	}
}

const listedExtensions = ".go .py .pyi .md .mdx .yaml .yml .json .jsonl .jsonc .toml .ts .tsx .js .jsx .mjs .cjs .sh .bash .zsh .fish .ps1 .rs .txt .html .css .scss .sql .tf .hcl .ipynb .lock .xml .csv .proto .graphql .vue .svelte .swift .kt .java .c .h .cc .cpp .hpp .rb .lua .nix .env .ini .cfg .conf"

func fileLine(kind, field string, value ir.Value) logline.Line {
	return build(logline.Firing{Call: &ir.Call{Kind: kind, Fields: map[string]ir.Value{field: value}}})
}

func TestBuildListsEveryExtensionForEveryFileKind(t *testing.T) {
	for extension := range strings.FieldsSeq(listedExtensions) {
		for _, c := range []struct{ kind, field, path string }{
			{ir.KindWrite, ir.FieldFilePath, "/project/file" + strings.ToUpper(extension)},
			{ir.KindEdit, ir.FieldFilePath, `C:\project\file` + extension},
			{ir.KindNotebook, ir.FieldNotebookPath, "file" + extension},
			{ir.KindPatch, ir.FieldCommand, "*** Begin Patch\n*** Add File: file" + extension + "\n+x\n*** End Patch\n"},
		} {
			if got := fileLine(c.kind, c.field, stringValue(c.path)).Extension; got != extension {
				t.Errorf("%s %q = %q; want %q", c.kind, c.path, got, extension)
			}
		}
	}
}

func TestBuildReadsTheLastPathElementAndFirstPatchFile(t *testing.T) {
	for _, c := range []struct{ path, extension string }{
		{"", "none"},
		{"file", "none"},
		{".bashrc", "none"},
		{"/dir.go/.bashrc", "none"},
		{`C:\dir.go\file`, "none"},
		{`C:\dir\a.PY`, ".py"},
		{"/dir.go/", "none"},
		{"file.", "other"},
		{".config.JSON", ".json"},
		{"a.tar.gz", "other"},
		{"file.gosecret-marker", "other"},
		{"file.unknown", "other"},
		{".go", "none"},
	} {
		if got := fileLine(ir.KindWrite, ir.FieldFilePath, stringValue(c.path)).Extension; got != c.extension {
			t.Errorf("extension of %q = %q; want %q", c.path, got, c.extension)
		}
	}
	for _, c := range []struct {
		kind, field string
		value       ir.Value
		want        string
	}{
		{ir.KindWrite, ir.FieldFilePath, ir.Value{Text: "x.go"}, "none"},
		{ir.KindWrite, ir.FieldNotebookPath, stringValue("x.go"), "none"},
		{ir.KindNotebook, ir.FieldFilePath, stringValue("x.go"), "none"},
		{ir.KindPatch, ir.FieldCommand, stringValue("*** Begin Patch\n*** Add File: a.py\n+x\n*** Add File: b.go\n+y\n*** End Patch\n"), ".py"},
		{ir.KindPatch, ir.FieldCommand, stringValue("*** Begin Patch\n*** Update File: a.py\n*** Move to: b.go\n*** End Patch\n"), ".go"},
		{ir.KindPatch, ir.FieldCommand, stringValue("not a patch"), "none"},
		{ir.KindPatch, ir.FieldCommand, ir.Value{Text: "*** Begin Patch\n*** Add File: a.py\n"}, "none"},
		{ir.KindShell, ir.FieldFilePath, stringValue("a.py"), ""},
	} {
		if got := fileLine(c.kind, c.field, c.value).Extension; got != c.want {
			t.Errorf("%s/%s extension = %q; want %q", c.kind, c.field, got, c.want)
		}
	}
}
