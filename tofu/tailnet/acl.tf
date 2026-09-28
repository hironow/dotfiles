# The tailnet's ACL, taken over from the retired exe stack.
#
# The first plan imports the live policy and replaces it with acl.hujson in
# the same apply: the only change is the retired stack's tags and their rules
# going away. expected-changes/import-acl.txt is the reviewed list; the step
# sheet checks first that no device still carries one of those tags.

# `tofu test` cannot import (its mock providers refuse), so the import is
# switched by adopt_live_acl: on for the real plan, off in tests/. It is a
# no-op once the ACL is in state, and can go after the first apply.
import {
  for_each = var.adopt_live_acl ? toset(["acl"]) : toset([])
  to       = tailscale_acl.this
  id       = each.value
}

resource "tailscale_acl" "this" {
  acl = file("${path.module}/acl.hujson")

  # State, not whatever the admin console holds, is the truth: an apply does
  # not stall on a policy edited there.
  overwrite_existing_content = true

  # A destroy would put the tailnet back on Tailscale's default policy (every
  # device reaching every other) or lock the owner out; it is refused. Moving
  # the ACL elsewhere is a `removed` block with destroy = false, as the old
  # stack did.
  lifecycle {
    prevent_destroy = true
  }
}
