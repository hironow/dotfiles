package rules

import (
	"strings"
	"testing"
)

const tailnetFixture = `terraform {
  backend "gcs" {
    bucket = "gen-ai-hironow-tofu-state"
    prefix = "tailnet"
  }
  encryption {
    key_provider "pbkdf2" "default" {
      passphrase = "OVERRIDDEN_BY_TF_ENCRYPTION_ENV"
    }
    state {
      enforced = true
    }
    plan {
      enforced = true
    }
  }
}
import {
  to = tailscale_acl.this
  for_each = var.adopt_live_acl
}
resource "tailscale_acl" "this" {
  acl = file("${path.module}/acl.hujson")
  lifecycle { prevent_destroy = true }
}
`

func tailnetBase() Inputs {
	return Inputs{tailnetGlob: map[string]any{tailnetMain: tailnetFixture, tailnetVariables: "# no encryption variable\n"}, tailnetVariables: "# no encryption variable\n"}
}

func tailnetEdit(old, replacement string) func(Inputs) {
	return func(in Inputs) {
		files := in[tailnetGlob].(map[string]any)
		files[tailnetMain] = strings.Replace(files[tailnetMain].(string), old, replacement, 1)
	}
}

func TestTailnetStatePosture(t *testing.T) {
	const (
		private    = "test_the_tailnets_state_does_not_touch_the_private_project"
		backend    = "test_the_tailnets_backend_is_the_old_personal_bucket_spelled_out"
		encryption = "test_the_tailnets_state_is_passphrase_encrypted_and_fails_closed"
		adopt      = "test_the_new_stack_imports_the_live_acl"
		protect    = "test_the_new_stack_cannot_destroy_the_acl"
	)
	runCases(t, tailnetStatePosture(), tailnetBase, []ruleCase{
		{"KMS provider", tailnetEdit("terraform {", "gcp_kms\nterraform {"), private},
		{"backend KMS", tailnetEdit("terraform {", "kms_encryption_key\nterraform {"), private},
		{"KMS variable reference", tailnetEdit("terraform {", "state_kms_key\nterraform {"), private},
		{"variable comment", edit(tailnetVariables, "# no encryption variable", "# state_kms_key"), private},
		{"wrong bucket", tailnetEdit("gen-ai-hironow-tofu-state", "other"), backend},
		{"wrong prefix", tailnetEdit(`prefix = "tailnet"`, `prefix = "other"`), backend},
		{"partial bucket", tailnetEdit(`bucket = "gen-ai-hironow-tofu-state"`, `bucket = var.bucket`), backend},
		{"duplicate backend", tailnetEdit("terraform {", "terraform {\nbackend \"gcs\" {}"), backend},
		{"missing backend", tailnetEdit(`backend "gcs"`, `backend "local"`), backend},
		{"duplicate encryption", tailnetEdit("  encryption {", "  encryption {}\n  encryption {"), encryption},
		{"no PBKDF2", tailnetEdit(`key_provider "pbkdf2"`, `key_provider "static"`), encryption},
		{"real passphrase", tailnetEdit("OVERRIDDEN_BY_TF_ENCRYPTION_ENV", "a-secret"), encryption},
		{"state not enforced", tailnetEdit("state {\n      enforced = true", "state {\n      enforced = false"), encryption},
		{"plan not enforced", tailnetEdit("plan {\n      enforced = true", "plan {\n      enforced = false"), encryption},
		{"first state wins", tailnetEdit("    state {", "    state {}\n    state {"), encryption},
		{"first plan wins", tailnetEdit("    plan {", "    plan {}\n    plan {"), encryption},
		{"no import", tailnetEdit("import {", "other {"), adopt},
		{"first import wins", tailnetEdit("import {", "import {}\nimport {"), adopt},
		{"wrong destination", tailnetEdit("tailscale_acl.this", "tailscale_acl.other"), adopt},
		{"Unicode destination boundary", tailnetEdit("tailscale_acl.this", "tailscale_acl.this猫"), adopt},
		{"Unicode variable boundary", tailnetEdit("var.adopt_live_acl", "var.adopt_live_acl猫"), adopt},
		{"no adoption reference", tailnetEdit("var.adopt_live_acl", "true"), adopt},
		{"destroy allowed", tailnetEdit("prevent_destroy = true", "prevent_destroy = false"), protect},
		{"other ACL", tailnetEdit("/acl.hujson", "/other.hujson"), protect},
		{"exact resource header", tailnetEdit(`resource "tailscale_acl"`, "resource  \"tailscale_acl\""), protect},
		{"first resource wins", tailnetEdit(`resource "tailscale_acl" "this" {`, "resource \"tailscale_acl\" \"this\" {}\nresource \"tailscale_acl\" \"this\" {"), protect},
		{"unclosed block", tailnetEdit("lifecycle { prevent_destroy = true }", "lifecycle { prevent_destroy = true"), protect},
		{"comment brace is counted", tailnetEdit("    prefix =", "    # }\n    prefix ="), backend},
		{"quoted brace is counted", tailnetEdit("    prefix =", "    example = \"}\"\n    prefix ="), backend},
	})
}

func TestTailnetPythonReading(t *testing.T) {
	for name, change := range map[string]func(Inputs){
		"Unicode whitespace":    tailnetEdit(`bucket =`, "bucket\u00a0=\u001c"),
		"hash comments only":    tailnetEdit("terraform {", "# gcp_kms kms_encryption_key state_kms_key\nterraform {"),
		"case sensitive":        tailnetEdit("terraform {", "GCP_KMS\nterraform {"),
		"raw backend comments":  tailnetEdit(`bucket =`, `# bucket =`),
		"raw resource comments": tailnetEdit("prevent_destroy =", "# prevent_destroy ="),
		"no AES assertion":      tailnetEdit("    state {", "    method \"unencrypted\" \"none\" {}\n    state {"),
		"second state ignored":  tailnetEdit("    plan {", "    state { enforced = false }\n    plan {"),
		"import boundary":       tailnetEdit("import {", "猫import {}\nimport {"),
		"universal newlines per file": func(in Inputs) {
			files := in[tailnetGlob].(map[string]any)
			files[tailnetMain] = strings.ReplaceAll(tailnetFixture, "\n", "\r")
		},
		"sort then join": func(in Inputs) {
			files := in[tailnetGlob].(map[string]any)
			files["tofu/tailnet/z.tf"] = files[tailnetMain]
			files[tailnetMain] = "# first file without final newline"
		},
		"raw braces in comments": tailnetEdit("    prefix =", "    # { }\n    prefix ="),
		"raw braces in strings":  tailnetEdit("    prefix =", "    example = \"{}\"\n    prefix ="),
	} {
		t.Run(name, func(t *testing.T) {
			in := tailnetBase()
			change(in)
			if got := tailnetStatePosture().Check(in); len(got) != 0 {
				t.Fatal(got)
			}
		})
	}
}

func TestTailnetUsesPlatformPathOrder(t *testing.T) {
	for _, goos := range []string{"windows", "linux", "darwin"} {
		for _, aclValid := range []bool{true, false} {
			t.Run(goos+"/aclValid="+map[bool]string{true: "true", false: "false"}[aclValid], func(t *testing.T) {
				in := tailnetBase()
				files := in[tailnetGlob].(map[string]any)
				importBlock := "import { to = tailscale_acl.this\nfor_each = var.adopt_live_acl }\n"
				// Keep only these two import blocks, before main.tf's other blocks.
				files[tailnetMain] = strings.Replace(tailnetFixture, "import {\n  to = tailscale_acl.this\n  for_each = var.adopt_live_acl\n}\n", "", 1)
				badImport := strings.Replace(importBlock, "tailscale_acl.this", "tailscale_acl.other", 1)
				files["tofu/tailnet/acl.tf"], files["tofu/tailnet/Z.tf"] = importBlock, badImport
				if !aclValid {
					files["tofu/tailnet/acl.tf"], files["tofu/tailnet/Z.tf"] = badImport, importBlock
				}
				got := tailnetStatePostureForOS(goos).Check(in)
				wantFailure := (goos == "windows") != aclValid
				if wantFailure {
					if len(got) != 1 || !strings.Contains(got[0].Message, "test_the_new_stack_imports_the_live_acl") {
						t.Fatalf("findings = %v; want the import fact", got)
					}
				} else if len(got) != 0 {
					t.Fatal(got)
				}
			})
		}
	}
}
