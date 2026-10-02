# What this file pins: the tailnet's policy after the Coder stack's
# retirement (Phase 7, 7.2).
#
#   - The retired stack's tags are gone: tag:exe-coder, tag:exe-workspace and
#     tag:agent, as tag owners and in every rule.
#   - Both break-glass rules stay, and so does the owner's full reach: losing
#     one is how an ACL push locks the owner out.
#   - The steiner stack's tags and its one rule stay as they were.
#   - The policy in state wins over the admin console's
#     (overwrite_existing_content), so an apply never stalls on an edit made
#     there.
#
# prevent_destroy and the import block are not visible to a tofu test;
# tests/unit/test_tailnet_stack.py reads them from the files.
#
# command = plan + mock_provider: offline, no credentials, nothing created.

mock_provider "tailscale" {}

variables {
  # tofu test's mock providers cannot import (acl.tf).
  adopt_live_acl = false
  tailnet        = "zz-synthetic.example"
  state_kms_key  = "projects/zz-synthetic-project/locations/asia-northeast1/keyRings/exe-state/cryptoKeys/tailnet-state"
}

run "the_retired_stacks_tags_are_gone" {
  command = plan

  assert {
    condition     = !strcontains(tailscale_acl.this.acl, "tag:exe-coder")
    error_message = "tag:exe-coder belonged to the retired Coder control-plane VM; nothing may still issue or reach it."
  }

  assert {
    condition     = !strcontains(tailscale_acl.this.acl, "tag:exe-workspace")
    error_message = "tag:exe-workspace belonged to the retired Coder workspace VMs."
  }

  assert {
    condition     = !strcontains(tailscale_acl.this.acl, "tag:agent")
    error_message = "tag:agent belonged to AI agents inside Coder workspaces; exe's tasks on google/ax never join the tailnet."
  }
}

run "the_owner_keeps_every_way_in" {
  command = plan

  assert {
    condition     = strcontains(tailscale_acl.this.acl, "\"src\":    [\"autogroup:admin\"],\n      \"dst\":    [\"*:*\"]")
    error_message = "break-glass #1 (the tailnet's admins reach everything) must stay: without it an ACL push can lock the owner out."
  }

  assert {
    condition     = strcontains(tailscale_acl.this.acl, "\"src\":    [\"group:owners\"],\n      \"dst\":    [\"*:*\"]") && strcontains(tailscale_acl.this.acl, "\"group:owners\": [\"hironow365@gmail.com\"]")
    error_message = "break-glass #2 (the owner's email reaches everything) must stay, with the owner in group:owners."
  }

  assert {
    condition     = strcontains(tailscale_acl.this.acl, "\"src\":    [\"tag:owner\"],\n      \"dst\":    [\"*:*\"]")
    error_message = "the owner's own devices (tag:owner) must keep reaching everything."
  }
}

run "the_other_stacks_tags_are_untouched" {
  command = plan

  assert {
    condition     = strcontains(tailscale_acl.this.acl, "\"tag:steiner\":          [\"autogroup:admin\"]") && strcontains(tailscale_acl.this.acl, "\"tag:steiner-upstream\": [\"autogroup:admin\"]")
    error_message = "the steiner stack mints keys for tag:steiner and reads from tag:steiner-upstream; both tag owners must stay."
  }

  assert {
    condition     = strcontains(tailscale_acl.this.acl, "\"src\":    [\"tag:steiner\"],\n      \"dst\":    [\"tag:steiner-upstream:8080\"]")
    error_message = "the steiner workload's one rule (its upstream's port 8080, nothing else) must stay as it was."
  }
}

run "the_policy_in_state_wins_over_the_console" {
  command = plan

  assert {
    condition     = tailscale_acl.this.overwrite_existing_content == true
    error_message = "overwrite_existing_content must be true, or an apply stalls on any edit made in the admin console."
  }
}
