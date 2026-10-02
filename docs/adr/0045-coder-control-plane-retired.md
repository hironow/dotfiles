# 0045. The Coder control plane is retired, and what outlived it

**Date:** 2026-10-01
**Status:** Accepted (operator directive; destroyed 2026-10-01 with the
operator's explicit GO).

## Context

`exe.hironow.dev` was a GCE control plane: a Coder server on one VM, reached
through a Cloudflare Argo tunnel with Zero Trust Access in front of it, with
Cloud SQL Postgres behind it and Tailscale joining the workspaces. ADRs 0002,
0004, 0007, 0008, 0009, 0010, 0011 and 0012 describe how it was built and why.

It had been mothballed for a while — the VM destroyed, the database stopped — so
it cost little and did nothing. That is the state in which infrastructure rots:
the stack still held credentials, a shared IAM pool, a tunnel, DNS records and a
database, and nobody was watching any of them. The decision was to finish the
job: destroy it, and be explicit about the handful of things that must survive
its destruction.

The replacement mechanism has since been moved out of this repository as well,
so what remains here is the generic agent base environment and the tailnet
policy — dotfiles no longer defines, pins or operates any execution stack.

## Decision

**The stack is destroyed.** One targeted plan per step, each reviewed against a
change list prepared in advance, applied by the manager with the old project's
identity supplied per command, and the destroy itself only after the operator's
explicit GO. The state is empty and the shared project the stack lived in is
intact: 14 Cloud Run services and 2 jobs untouched, the service accounts down by
exactly the three the stack owned, one Artifact Registry repository gone.

**The database leaves a 30-day copy.** The instance was started before deletion,
because Cloud SQL does not promise a final backup for a stopped instance, and
both deletion protections were lifted in the same plan. The final backup is
retained **30 days** after the instance's deletion. A 30-day window on a stack
nobody is running is the cheaper half of the choice between an export (which
would have needed a bucket outliving the stack) and a final backup.

**Three classes of object are FORGOTTEN, never destroyed.** Each left the state
through a `removed` block with `destroy = false`, in one targeted plan applied
before any destroy plan existed — because `tofu plan -destroy` ignores those
blocks and would have deleted all of them.

- **The tailnet's ACL.** It is the tailnet's whole authorization model and
  outlives any stack. Destroying it would have left every device reaching every
  other, or locked the owner out.
- **The Workload Identity pool `github`.** It **pre-existed this stack** — an
  `import` block adopted it rather than failing on "entity already exists" — and
  two other providers live in it, one for another repository and one owner-wide,
  with service accounts bound through them. A destroy would have taken the pool
  and broken deploys that have nothing to do with this stack. Only the provider
  this stack created, its publishing service account and that binding were
  destroyed.
- **Eight Cloudflare objects**: a tunnel and its config, two DNS records, two
  Access policies, a service token and an Access application. The operator chose
  to keep them so the `exe.` subdomain stays reusable. They are now **unmanaged
  and in no state file**: nothing in this repository reads, plans or deletes
  them, and no recipe needs a Cloudflare API token. Their GCP-side copies (the
  tunnel credentials and the token's client id and secret, in Secret Manager)
  were destroyed with the stack; the credentials can be fetched from Cloudflare
  again and the token rotated there.

**The general rule, which is the part worth keeping:** anything that entered a
stack's state through an `import` block pre-existed that stack, so it is
forgotten rather than destroyed. The pool is the case that makes it concrete —
the `import` was the signal, and reading the live state before the window was
what turned it from a destroy into a forget.

**The tailnet gets its own stack and its own state home.** `tofu/tailnet` took
the ACL over by import, after the old stack let go of it, so the policy never had
two owners and never had none. Its state lives in the **old personal project's**
bucket under the prefix `tailnet`, encrypted by passphrase (pbkdf2, aes_gcm,
enforced for the state and for saved plans) with its own passphrase file rather
than the retired stack's. Not the exe project's bucket and not a key that project
owns: this repository is public and that project is private, so either would put
a private identifier in a public repo's backend and tie the two lifetimes
together.

## Consequences

- **The `cdr` commands are gone**, with the control plane they drove. `ax-job`
  and `ax-exec` are their replacements. A recipe prunes the symlinks the retired
  installer left in `~/.local/bin`, removing only ones whose target is gone.
- **Nothing plans the Cloudflare objects.** That is deliberate, and it is also a
  gap: a change made to them in Cloudflare will never show up as drift here. If
  they are to be managed again, they are imported like any pre-existing resource.
- **The ACL now has exactly one owner**, and that owner refuses to destroy it
  (`prevent_destroy`). Moving it again means a `removed` block with
  `destroy = false` and an import elsewhere — the sequence this retirement used.
- **The tailnet's state depends on the old personal project's bucket.** If that
  bucket goes, the state goes; the ACL does not. A fresh state re-imports the
  live policy, and `tofu/tailnet/README.md` carries the migration steps.
- **The ADRs that described the stack stay.** 0002, 0004, 0007 through 0012 are
  accepted and therefore immutable: the record of why something was built
  outlives the thing. `tests/unit/test_no_exe_residue.py` asserts their
  directory is NOT removed, alongside asserting the stack's own paths are.
- **A final backup is not a plan.** It expires 30 days after the deletion, and
  nothing renews it. After that the database is gone for good, which is the
  intended end state rather than an oversight.
