"""The retired Coder stack forgets what outlives it, and destroys the rest.

Three of the old stack's state entries are NOT its own to delete, and eight
more the operator decided to keep (Phase 7, M74):

  - `tailscale_acl.this`      — the tailnet's policy; tofu/tailnet imports it;
  - `google_iam_workload_identity_pool.github` — SHARED. The pool pre-existed
    this stack (an `import` block adopted it) and other repositories' providers
    and deployers live in it, so a destroy would break them;
  - the eight Cloudflare objects — the operator parks them unmanaged, in no
    state, to keep the `exe.` subdomain reusable.

The rule the first two make concrete: anything that entered the state through
an `import` block pre-existed the stack, so it is FORGOTTEN, never destroyed.

`tofu plan -destroy` ignores `removed` blocks, so the ten leave the state in
one targeted plan of their own, held to `expected-changes/retire-2-forget.txt`,
BEFORE any destroy plan exists. These tests pin that list against the stack so
the two cannot drift, and pin the second half of the Cloudflare decision: no
step of the retirement may need a Cloudflare API token, because nothing in the
configuration reads a Cloudflare attribute any more.

tofu/tailnet's state is pinned here too (M77): it stays in the OLD personal
project's bucket, encrypted by passphrase like the old stack. The exe project
is private and this repo is public, so putting the public repo's tailnet state
in that project's bucket, under a key it owns, would tie the two together.

These read the stacks' files. A `tofu test` can see neither a `removed` block,
an `import`, a backend nor an `encryption` block.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OLD = REPO / "tofu" / "exe"
TAILNET = REPO / "tofu" / "tailnet"
JUSTFILE = REPO / "justfile"

# The old personal project's state bucket. It already holds the old stack's
# own state (tofu/exe/main.tf) and is not a private identifier.
OLD_STATE_BUCKET = "gen-ai-hironow-tofu-state"

# The ten addresses that leave the old stack's state and stay live.
FORGOTTEN = {
    "tailscale_acl.this",
    "google_iam_workload_identity_pool.github",
    "cloudflare_zero_trust_tunnel_cloudflared.exe",
    "cloudflare_zero_trust_tunnel_cloudflared_config.exe",
    "cloudflare_dns_record.coder",
    "cloudflare_dns_record.sandbox_wildcard",
    "cloudflare_zero_trust_access_policy.coder_owner",
    "cloudflare_zero_trust_access_policy.coder_service_token",
    "cloudflare_zero_trust_access_service_token.coder_cli",
    "cloudflare_zero_trust_access_application.coder",
}


def stack_text(stack: Path) -> str:
    return "\n".join(tf.read_text() for tf in sorted(stack.glob("*.tf")))


def code_only(text: str) -> str:
    """`text` with its `#` comments blanked out.

    The stack's comments quote the very addresses these tests ban, to say why
    they are banned; a reference and an explanation must not read alike.
    """
    return re.sub(r"(?m)#.*$", "", text)


def blocks(text: str, header: str) -> list[str]:
    """Every block body whose header matches `header` (a regex)."""
    bodies: list[str] = []
    for m in re.finditer(header + r"\s*\{", text):
        depth, i = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        bodies.append(text[m.end() : i - 1])
    return bodies


def removed_blocks(stack: Path) -> dict[str, bool]:
    """`removed` block address -> its `lifecycle { destroy = ... }` value."""
    out: dict[str, bool] = {}
    for body in blocks(stack_text(stack), r"(?m)^removed"):
        frm = re.search(r"(?m)^\s*from\s*=\s*(\S+)", body)
        destroy = re.search(r"(?m)^\s*destroy\s*=\s*(true|false)", body)
        assert frm, f"a removed block has no `from`: {body!r}"
        assert destroy, (
            f"the removed block for {frm.group(1)} sets no lifecycle destroy: "
            "OpenTofu needs it spelled out, and the reader needs to see which it is"
        )
        out[frm.group(1)] = destroy.group(1) == "true"
    return out


def change_list(path: Path) -> list[str]:
    """An expected-changes file's markers, comments and blanks dropped."""
    return [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


# --- the forget set ----------------------------------------------------


def test_exactly_the_ten_shared_or_parked_objects_are_forgotten() -> None:
    forgotten = {addr for addr, destroy in removed_blocks(OLD).items() if not destroy}
    assert forgotten == FORGOTTEN, (
        "the retirement forgets exactly ten addresses; anything else here either "
        "deletes something the stack does not own, or destroys something it does"
    )


def test_the_forget_plans_change_list_matches_the_stack() -> None:
    """The reviewed list and the stack cannot drift: one is read in the
    operator's window to approve what the other produced."""
    listed = change_list(OLD / "expected-changes" / "retire-2-forget.txt")
    assert sorted(listed) == sorted(f". {addr}" for addr in FORGOTTEN), (
        "retire-2-forget.txt must hold exactly the ten forget markers ('.')"
    )


def test_the_database_plans_change_list_is_one_change() -> None:
    listed = change_list(OLD / "expected-changes" / "retire-1-database.txt")
    assert listed == ["~ google_sql_database_instance.coder"]


def test_the_retirements_first_change_list_is_not_the_superseded_one() -> None:
    """retire-1-hand-over.txt bundled the ACL's forget with the database's
    change. M74 split them: the forget grew to ten and goes on its own."""
    assert not (OLD / "expected-changes" / "retire-1-hand-over.txt").exists()


# --- the shared Workload Identity pool ---------------------------------


def test_the_shared_wif_pool_is_neither_declared_nor_imported() -> None:
    text = stack_text(OLD)
    assert not re.search(r'resource\s+"google_iam_workload_identity_pool"', text), (
        "the pool is shared with other repositories: this stack must not own it"
    )
    for body in blocks(text, r"(?m)^import"):
        assert "google_iam_workload_identity_pool.github" not in body, (
            "an import block would adopt the shared pool back into this state"
        )


def test_the_pools_own_provider_is_still_destroyed_by_its_literal_id() -> None:
    """Only this stack's provider inside the pool goes. With the pool resource
    gone, the provider names the pool by its literal id, so no reference
    resurrects it."""
    provider = blocks(
        stack_text(OLD),
        r'resource\s+"google_iam_workload_identity_pool_provider"\s+"\w+"',
    )
    assert len(provider) == 1
    assert re.search(r'workload_identity_pool_id\s*=\s*"github"', provider[0])
    assert re.search(
        r'workload_identity_pool_provider_id\s*=\s*"github-actions"', provider[0]
    )


def test_nothing_reads_an_attribute_of_the_forgotten_pool() -> None:
    """A reference would make the forgotten pool a dependency again, and an
    attribute of it cannot be read once it has left the state."""
    text = code_only(stack_text(OLD))
    for body in blocks(text, r"(?m)^removed"):
        text = text.replace(body, "")
    assert not re.search(r"google_iam_workload_identity_pool\.github\s*\.", text)


# --- Cloudflare: parked, and no token needed ---------------------------


def test_the_stack_declares_no_cloudflare_object() -> None:
    text = code_only(stack_text(OLD))
    assert not re.search(r'(?m)^resource\s+"cloudflare_', text)
    assert not re.search(r'(?m)^data\s+"cloudflare_', text)


def test_no_step_of_the_retirement_configures_the_cloudflare_provider() -> None:
    """Neither the forget nor the destroy may need CLOUDFLARE_API_TOKEN. With
    no provider block, no data source and no resource, nothing calls
    Cloudflare; the provider stays in required_providers only so the state's
    Cloudflare entries still decode until the forget drops them."""
    text = stack_text(OLD)
    assert not blocks(text, r'(?m)^provider\s+"cloudflare"')
    required = blocks(text, r"(?m)^\s*required_providers")
    assert required and re.search(r"(?m)^\s*cloudflare\s*=", required[0]), (
        "the forget still has to decode the Cloudflare entries in the state"
    )


def test_nothing_reads_a_cloudflare_attribute() -> None:
    text = code_only(stack_text(OLD))
    for body in blocks(text, r"(?m)^removed"):
        text = text.replace(body, "")
    leaked = re.findall(r"cloudflare_[a-z0-9_]+\.[a-z0-9_]+\.[a-z0-9_]+", text)
    assert leaked == [], f"these still read a Cloudflare attribute: {leaked}"


def test_no_exe_recipe_demands_a_cloudflare_api_token() -> None:
    """A guard for a credential the stack cannot use would stop the operator's
    window on a secret nobody needs."""
    assert "CLOUDFLARE_API_TOKEN:?" not in JUSTFILE.read_text()


# --- tofu/tailnet: state in the old personal project (M77) -------------


def test_the_tailnets_state_does_not_touch_the_private_project() -> None:
    """tofu/tailnet stays in this public repo, so its state stays in the old
    PERSONAL project's bucket: a bucket named after the private project, or a
    key that project owns, would tie the public repo to it."""
    text = code_only(stack_text(TAILNET))
    for forbidden in ("gcp_kms", "kms_encryption_key", "state_kms_key"):
        assert forbidden not in text, (
            f"{forbidden} ties the tailnet's state to the private exe project"
        )
    assert not (TAILNET / "variables.tf").read_text().count("state_kms_key")


def test_the_tailnets_backend_is_the_old_personal_bucket_spelled_out() -> None:
    """Both values are public, so they are literals: a partial backend config
    could start a second, empty state on a typo."""
    backend = blocks(stack_text(TAILNET), r'(?m)^\s*backend\s+"gcs"')
    assert len(backend) == 1
    assert re.search(rf'bucket\s*=\s*"{re.escape(OLD_STATE_BUCKET)}"', backend[0])
    assert re.search(r'prefix\s*=\s*"tailnet"', backend[0])


def test_the_tailnets_state_is_passphrase_encrypted_and_fails_closed() -> None:
    """Like the old stack: pbkdf2 + aes_gcm, enforced for state AND saved
    plans, with a sentinel passphrase in the file so a run without
    TF_ENCRYPTION is caught at once instead of writing state nobody can read
    back."""
    encryption = blocks(stack_text(TAILNET), r"(?m)^\s*encryption")
    assert len(encryption) == 1
    body = encryption[0]
    assert re.search(r'key_provider\s+"pbkdf2"\s+"default"', body)
    assert re.search(r'passphrase\s*=\s*"OVERRIDDEN_BY_TF_ENCRYPTION_ENV"', body), (
        "a real passphrase must never be in the repo; the sentinel fails closed"
    )
    for section in ("state", "plan"):
        inner = blocks(body, rf"(?m)^\s*{section}")
        assert inner and re.search(r"enforced\s*=\s*true", inner[0]), (
            f"{section} encryption must be enforced: the ACL's state carries "
            "the tailnet's policy"
        )


def test_the_tailnet_recipes_supply_the_passphrase_and_no_backend_config() -> None:
    text = JUSTFILE.read_text()
    assert "_tailnet-encryption" in text, (
        "the recipes must build TF_ENCRYPTION from the local passphrase file, "
        "as the old stack's _exe-encryption does"
    )
    assert "tofu/tailnet.passphrase" in text or "tailnet.passphrase" in text
    init = re.search(r"(?m)^tailnet-init.*\n(?:[ \t]+.*\n)*", text)
    assert init and "backend-config" not in init.group(0), (
        "the backend is spelled out in main.tf; backend.hcl is gone"
    )
