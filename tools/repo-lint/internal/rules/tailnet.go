package rules

import (
	"fmt"
	"runtime"
	"slices"
	"strings"
)

const (
	tailnetGlob      = "tofu/tailnet/*.tf"
	tailnetMain      = "tofu/tailnet/main.tf"
	tailnetVariables = "tofu/tailnet/variables.tf"
)

// tailnetStatePosture ports the raw text checks of test_coder_retirement.py
// and test_tailnet_handover.py. Runtime guards also live in the sandbox suite.
func tailnetStatePosture() Rule {
	return tailnetStatePostureForOS(runtime.GOOS)
}

func tailnetStatePostureForOS(goos string) Rule {
	r := factRule("tailnet-state-posture", "the tailnet keeps its personal backend, passphrase encryption, ACL import and destroy guard",
		[]string{tailnetGlob, tailnetVariables}, []scriptFact{
			fact("test_the_tailnets_state_does_not_touch_the_private_project", tailnetNoPrivateKey),
			fact("test_the_tailnets_backend_is_the_old_personal_bucket_spelled_out",
				tailnetBlock(`(?m)^\s*backend\s+"gcs"`, true,
					pyMatches(tailnetGlob, `bucket\s*=\s*"gen-ai-hironow-tofu-state"`, `prefix\s*=\s*"tailnet"`))),
			fact("test_the_tailnets_state_is_passphrase_encrypted_and_fails_closed",
				tailnetBlock(`(?m)^\s*encryption`, true,
					pyMatches(tailnetGlob, `key_provider\s+"pbkdf2"\s+"default"`, `passphrase\s*=\s*"OVERRIDDEN_BY_TF_ENCRYPTION_ENV"`),
					tailnetBlock(`(?m)^\s*state`, false, pyMatches(tailnetGlob, `enforced\s*=\s*true`)),
					tailnetBlock(`(?m)^\s*plan`, false, pyMatches(tailnetGlob, `enforced\s*=\s*true`)))),
			fact("test_the_new_stack_imports_the_live_acl",
				tailnetBlock(`\bimport`, false, pyMatches(tailnetGlob, `to\s*=\s*tailscale_acl\.this\b`, `for_each\s*=\s*var\.adopt_live_acl\b`))),
			fact("test_the_new_stack_cannot_destroy_the_acl",
				tailnetBlock(`resource "tailscale_acl" "this"`, false,
					pyMatches(tailnetGlob, `prevent_destroy\s*=\s*true`, `acl\s*=\s*file\("\$\{path\.module\}/acl\.hujson"\)`))),
		})
	check := r.Check
	r.Inputs[0].FilesystemGlob = true
	r.Check = func(in Inputs) []Finding {
		files, _ := in[tailnetGlob].(map[string]any)
		paths := make([]string, 0, len(files))
		for path := range files {
			paths = append(paths, path)
		}
		slices.SortFunc(paths, func(a, b string) int {
			if goos == "windows" {
				// PureWindowsPath compares lowercased path parts.
				a, b = pyLower(a), pyLower(b)
			}
			return strings.Compare(a, b)
		})
		texts := make([]string, 0, len(paths))
		for _, path := range paths {
			text, _ := files[path].(string)
			texts = append(texts, universalNewlines.Replace(text))
		}
		return check(Inputs{tailnetGlob: strings.Join(texts, "\n"), tailnetVariables: in[tailnetVariables]})
	}
	return r
}

func tailnetNoPrivateKey(files map[string]string) []string {
	code := pyCompile(`(?m)#.*$`).re.ReplaceAllString(files[tailnetGlob], "")
	out := runOn(tailnetGlob, code, []factCheck{lacks(tailnetGlob, "gcp_kms", "kms_encryption_key", "state_kms_key")})
	return append(out, lacks(tailnetVariables, "state_kms_key")(files)...)
}

// tailnetBlock counts raw braces, including braces in strings and comments,
// just as the removed Python readers did. A missing closing brace fails.
func tailnetBlock(header string, exactlyOne bool, checks ...factCheck) factCheck {
	pattern := pyCompile(header + `\s*\{`)
	return func(files map[string]string) []string {
		text := files[tailnetGlob]
		var bodies []string
		for _, loc := range pattern.re.FindAllStringIndex(text, -1) {
			if pattern.lead && !pyBoundaryAt(text, loc[0]) {
				continue
			}
			depth, end := 1, loc[1]
			for depth > 0 && end < len(text) {
				switch text[end] {
				case '{':
					depth++
				case '}':
					depth--
				}
				end++
			}
			if depth > 0 {
				return []string{fmt.Sprintf("%s: unclosed block %s", tailnetGlob, header)}
			}
			bodies = append(bodies, text[loc[1]:end-1])
			if !exactlyOne {
				break
			}
		}
		if len(bodies) == 0 || exactlyOne && len(bodies) != 1 {
			return []string{fmt.Sprintf("%s: expected %s block %s, found %d", tailnetGlob, map[bool]string{true: "exactly one", false: "a first"}[exactlyOne], header, len(bodies))}
		}
		return runOn(tailnetGlob, bodies[0], checks)
	}
}
