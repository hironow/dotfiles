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

These read the stack's files. A `tofu test` can see neither a `removed` block
nor an `import`.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OLD = REPO / "tofu" / "exe"
JUSTFILE = REPO / "justfile"

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
