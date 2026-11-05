package logline

import (
	"regexp"
	"strings"

	"github.com/hironow/dotfiles/tools/agent-hooks/internal/applypatch"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/ir"
	"github.com/hironow/dotfiles/tools/agent-hooks/internal/pyshlex"
)

var (
	assignment = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]*=`)
	programs   = wordSet("git gh just mise go gofmt golangci-lint uv uvx python python3 ruff ty bun bunx node " +
		"npm npx pnpm yarn corepack pip pip3 poetry pipenv make rtk docker podman kubectl gcloud tofu terraform " +
		"cargo rustc codex claude agy pi ls cat grep rg find fd sed awk jq yq curl wget cd echo mkdir rm cp mv " +
		"chmod touch head tail wc sort diff tar ssh sudo env bash sh zsh pwsh brew xargs tee test sleep printf")
	subcommands = map[string]map[string]bool{
		"git": wordSet("status diff log show add commit push pull fetch checkout switch branch merge rebase reset " +
			"restore stash tag worktree clone init remote rev-parse cherry-pick revert blame grep ls-files config submodule clean mv rm"),
		"gh":     wordSet("pr issue run repo api release workflow auth search browse"),
		"go":     wordSet("build test run vet mod get install fmt generate work env version tool doc list clean"),
		"uv":     wordSet("run sync add remove lock pip tool venv python init export tree build publish"),
		"bun":    wordSet("install add remove run test x build update pm init create outdated"),
		"docker": wordSet("run build compose ps exec logs images pull push stop rm start inspect network volume system buildx"),
		"mise":   wordSet("install use exec x run ls which upgrade doctor trust settings env prune outdated self-update where current"),
		"gcloud": wordSet("compute run iam projects auth config builds storage sql container functions secrets " +
			"services logging artifacts alpha beta"),
		"kubectl":   wordSet("get describe apply delete logs exec create edit rollout port-forward config scale patch top"),
		"tofu":      wordSet("init plan apply destroy fmt validate test state output import workspace providers show console"),
		"terraform": wordSet("init plan apply destroy fmt validate test state output import workspace providers show console"),
		"npm":       wordSet("install i ci add run test exec publish update"),
		"pnpm":      wordSet("install i ci add run test exec publish update"),
		"yarn":      wordSet("install i ci add run test exec publish update"),
		"pip":       wordSet("install uninstall freeze list show"),
		"pip3":      wordSet("install uninstall freeze list show"),
		"cargo":     wordSet("build test run check clippy fmt add update install doc bench new init publish"),
		"rtk":       wordSet("rewrite hook gain discover init git ls grep find read test err log json deps env summary diff"),
		"codex":     wordSet("exec review resume login mcp apply"),
		"brew":      wordSet("install uninstall upgrade update list info search bundle services tap cleanup doctor outdated"),
	}
	extensions = wordSet(".go .py .pyi .md .mdx .yaml .yml .json .jsonl .jsonc .toml .ts .tsx .js .jsx .mjs .cjs " +
		".sh .bash .zsh .fish .ps1 .rs .txt .html .css .scss .sql .tf .hcl .ipynb .lock .xml .csv .proto .graphql " +
		".vue .svelte .swift .kt .java .c .h .cc .cpp .hpp .rb .lua .nix .env .ini .cfg .conf")
)

func commandDetails(command string) (program, subcommand string) {
	words, err := pyshlex.Split(command)
	if err != nil {
		return "other", ""
	}
	for len(words) > 0 && assignment.MatchString(words[0]) {
		words = words[1:]
	}
	if len(words) == 0 {
		return "other", ""
	}
	name := words[0][strings.LastIndexByte(words[0], '/')+1:]
	program = fixed(name, programs)
	if list, ok := subcommands[program]; ok && len(words) > 1 {
		subcommand = fixed(words[1], list)
	}
	return program, subcommand
}

func fileExtension(call *ir.Call) string {
	field := ir.FieldFilePath
	switch call.Kind {
	case ir.KindNotebook:
		field = ir.FieldNotebookPath
	case ir.KindPatch:
		field = ir.FieldCommand
	}
	value := call.Fields[field]
	if !value.IsString {
		return "none"
	}
	path := value.Text
	if call.Kind == ir.KindPatch {
		paths := applypatch.FilePaths(path)
		if len(paths) == 0 {
			return "none"
		}
		path = paths[0]
	}
	name := path[strings.LastIndexAny(path, `/\`)+1:]
	dot := strings.LastIndexByte(name, '.')
	if dot <= 0 {
		return "none"
	}
	return fixed(strings.ToLower(name[dot:]), extensions)
}
