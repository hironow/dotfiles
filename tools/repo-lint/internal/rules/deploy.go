package rules

import "regexp"

const deployScriptPath = "scripts/deploy.sh"

var (
	// hostDumpPath is a per-host dump/<host>/ path.
	hostDumpPath = regexp.MustCompile(`dump/[^/\s]*\$?\{?host`)
	// sharedGitInclude is an [include] of shared.gitconfig; a comment that
	// names the file is fine.
	sharedGitInclude = regexp.MustCompile(`path\s*=\s*\S*shared\.gitconfig`)
)

// deploySharedConfig: deploy distributes shared config to every machine, so
// it never reads a host's dump/<host>/ copy (ADR 0030), and it never
// re-includes shared.gitconfig, which would clobber a machine's own override
// such as gpgsign=false on a keyless host (ADR 0033, ADR 0021). The policy
// covers the whole script, Unix path and Windows branch alike.
func deploySharedConfig() Rule {
	const id = "deploy-shared-config"
	return Rule{
		ID:     id,
		Why:    "deploy reads no per-host dump path and includes no shared.gitconfig (ADR 0030, 0033)",
		Inputs: []Input{{Path: deployScriptPath, Format: Text}},
		Check: func(in Inputs) []Finding {
			r := &report{rule: id, path: deployScriptPath}
			text, _ := in[deployScriptPath].(string)
			if m := hostDumpPath.FindString(text); m != "" {
				r.add("deploy reads a per-host path %q; the config it distributes is the shared dump/ copy (ADR 0030)", m)
			}
			if m := sharedGitInclude.FindString(text); m != "" {
				r.add("deploy includes shared.gitconfig (%q); it would clobber a machine's own override (ADR 0033, 0021)", m)
			}
			return r.out
		},
	}
}
