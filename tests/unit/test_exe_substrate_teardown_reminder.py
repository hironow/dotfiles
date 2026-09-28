"""Destroying exe-cluster says how to remove the Substrate install (M53 B4).

The Substrate install (terraform_data.ate_system) runs upstream's ate-setup and
leaves what it creates outside tofu state: ate-system, the ate.dev CRDs, the
podcertificate trust bundles. The designed way to remove them is
`just exe-substrate-teardown <sha> <version>`, from the exact commit that
installed them. It is deliberately NOT a destroy-time provisioner on the
install: that resource is replaced on every repin, and a destroy provisioner
would then delete the CRDs, and with them this stack's WorkerPool, before
the reinstall.

What guards the teardown instead: terraform_data.substrate_teardown_reminder
holds the installed pin in `input`, which is updated in place and never
replaces, and prints the exact command when exe-cluster is destroyed. A tofu
test cannot see provisioners, so this test reads the stack.
"""

from __future__ import annotations

import re
from pathlib import Path

CLUSTER = Path(__file__).resolve().parents[2] / "tofu" / "exe-cluster"


def resource(kind: str, name: str) -> str:
    """The body of one resource block in the stack."""
    for tf in sorted(CLUSTER.glob("*.tf")):
        text = tf.read_text()
        m = re.search(rf'resource "{kind}" "{name}" \{{', text)
        if not m:
            continue
        depth, i = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        return text[m.end() : i - 1]
    raise AssertionError(f"no {kind}.{name} in tofu/exe-cluster")


def test_the_reminder_holds_the_installed_pin_and_never_replaces() -> None:
    body = resource("terraform_data", "substrate_teardown_reminder")
    assert re.search(r"sha\s*=\s*local\.pins\.substrate\.sha", body)
    assert re.search(r"version\s*=\s*local\.pins\.substrate\.version", body)
    assert "triggers_replace" not in body


def test_destroying_the_stack_prints_the_teardown_command() -> None:
    body = resource("terraform_data", "substrate_teardown_reminder")
    assert re.search(r"when\s*=\s*destroy", body)
    assert "just exe-substrate-teardown ${self.input.sha} ${self.input.version}" in body


def test_the_install_itself_has_no_destroy_step() -> None:
    # A repin replaces the install; a destroy step there would tear down the
    # CRDs, and this stack's WorkerPool with them, on every repin.
    assert not re.search(
        r"when\s*=\s*destroy", resource("terraform_data", "ate_system")
    )
