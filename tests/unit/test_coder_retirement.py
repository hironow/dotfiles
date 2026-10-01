"""What the Coder stack's retirement left behind: the tailnet's state posture.

The retirement itself is finished and its stack is gone, so the assertions that
read `tofu/exe` went with it. They did a job that cannot be done twice: they held
the ten `removed` blocks (the tailnet's ACL, the SHARED Workload Identity pool
`github`, and the eight Cloudflare objects the operator parked) to the reviewed
change list, and they proved that no step of the retirement could call Cloudflare.
With the stack destroyed and its state empty, a test that still read its files
would only assert that a directory is missing -- which
`tests/unit/test_no_exe_residue.py` does properly, by path.

What outlives the retirement, and therefore stays here: `tofu/tailnet` took the
ACL over, and WHERE its state lives is a standing property rather than a one-off
step. That repo is public and the exe project is private, so the state sits in
the OLD personal project's bucket under a passphrase -- not in the exe project's
bucket, and not under a key that project owns, either of which would tie the two
together for as long as both exist.

These read the stack's files. A `tofu test` can see neither a backend nor an
`encryption` block.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TAILNET = REPO / "tofu" / "tailnet"
JUSTFILE = REPO / "justfile"

# The old personal project's state bucket, which the retired stack also used. It
# is not a private identifier.
OLD_STATE_BUCKET = "gen-ai-hironow-tofu-state"


def stack_text(stack: Path) -> str:
    return "\n".join(tf.read_text() for tf in sorted(stack.glob("*.tf")))


def code_only(text: str) -> str:
    """`text` with its `#` comments blanked out.

    The stack's comments quote the very names these tests ban, to say why they
    are banned; a reference and an explanation must not read alike.
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
    """pbkdf2 + aes_gcm, enforced for the state AND for saved plans, with a
    sentinel passphrase in the file so a run without TF_ENCRYPTION is caught at
    once instead of writing state nobody can read back."""
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
    """Its own passphrase file, which is why the retired stack's going did not
    take this stack's state with it."""
    text = JUSTFILE.read_text()
    assert "_tailnet-encryption" in text, (
        "the recipes must build TF_ENCRYPTION from the local passphrase file"
    )
    assert "tailnet.passphrase" in text
    init = re.search(r"(?m)^tailnet-init.*\n(?:[ \t]+.*\n)*", text)
    assert init and "backend-config" not in init.group(0), (
        "the backend is spelled out in main.tf; backend.hcl is gone"
    )
