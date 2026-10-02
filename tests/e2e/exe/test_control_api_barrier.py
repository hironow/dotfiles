"""Plan F5 live: what stands between a task and Substrate's Control API.

L1's drain barrier (plan D2) holds only if nothing but the components it stops
can resume an actor. The Control API authenticates its callers but does not
authorize them (plan F1). W2 found that a task reaches it. With tunneled egress
armed, an actor's TCP leaves through atenet-egress, and the API sees the
gateway (manager-loop/reports/f5-control-api-audit.md). Two layers are left,
and this module tests each:

- Authentication, the guest's path. The API admits only a Kubernetes SA token
  for audience api.ate-system.svc, or a podidentity client certificate, and a
  guest has neither. So an unauthenticated call from the task is refused with
  UNAUTHENTICATED, and the guest has no /var/run/secrets.
- The network, the worker pod's path. tofu/exe-cluster/control_api.tf admits
  the API's port only from its callers, and nothing in the atespace, where a
  worker pod holds a certificate the API accepts. A probe pod in the atespace
  stands in for the worker pod: the policy admits nothing from that namespace,
  and the probe needs a python the worker image lacks. With
  EXE_E2E_API_POLICY=absent the probe must get an answer, which shows the path
  exists. With present it must not, and the callers must still work.

W3 (inbox M46) runs the module with EXE_E2E_API_POLICY=absent, has the policy
applied, then runs it again with present.
"""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Iterator

import pytest
from exe_live import Exe, stamp, utcnow

POLICY = os.environ.get("EXE_E2E_API_POLICY", "")
needs_policy_state = pytest.mark.skipif(
    POLICY not in ("absent", "present"),
    reason="EXE_E2E_API_POLICY=absent|present says whether control_api.tf is applied",
)

# A TLS handshake with the Control API at each target, with verification on.
# Nothing here trusts the cluster's CA, so a server that answers fails
# verification, and that failure is the proof it answered. No answer is a
# timeout, a reset or a refusal. A bare TCP connect proves nothing inside an
# actor (Phase 5, finding 5).
REACH = """
import socket, ssl, sys
ctx = ssl.create_default_context()
answered = []
for host in sys.argv[1:]:
    try:
        with socket.create_connection((host, 443), timeout=5) as s:
            with ctx.wrap_socket(s, server_hostname="api.ate-system.svc"):
                answered.append(host)
    except ssl.SSLCertVerificationError:
        answered.append(host)
    except OSError as exc:
        print(host, "no answer:", type(exc).__name__)
print("ANSWERED", " ".join(answered))
"""

# One unauthenticated gRPC call, ListActors with an empty message. -k because
# the guest cannot verify the server, and needs no trust in it: nothing is
# sent but the empty request, and the question is whether the API refuses it.
# A trailers-only refusal carries grpc-status in the response headers.
AUTH = """
printf '\\000\\000\\000\\000\\000' > /tmp/grpc-empty
curl -sk --http2 --max-time 10 -o /dev/null -D - \\
  -H 'content-type: application/grpc' -H 'te: trailers' \\
  --data-binary @/tmp/grpc-empty \\
  https://api.ate-system.svc/ateapi.Control/ListActors
echo "CURL $?"
if [ -e /var/run/secrets ]; then echo "SECRETS PRESENT"; ls -R /var/run/secrets; else echo "NO SECRETS"; fi
"""


@pytest.fixture(scope="module")
def task(exe: Exe) -> Iterator[str]:
    exe.wake("30m")
    name = exe.unique("e2e-f5")
    exe.apply_task(name)
    exe.wait_phase(name, "Running")
    yield name


def api_pod_ips(exe: Exe) -> list[str]:
    """The ate-api-server pods' own addresses: the headless Service's endpoints."""
    out = exe.kubectl(
        "-n",
        "ate-system",
        "get",
        "endpointslices",
        "-l",
        "kubernetes.io/service-name=api",
        "-o",
        "jsonpath={.items[*].endpoints[*].addresses[*]}",
    )
    return out.split()


def answered(output: str) -> list[str]:
    return output.strip().splitlines()[-1].split()[1:]


def test_a_task_cannot_authenticate_to_the_control_api(exe: Exe, task: str) -> None:
    out = exe.ax("ssh", task, "--", "sh", "-c", AUTH, timeout=60)
    # The guest's way in goes through the egress gateway, so it may answer.
    # Recorded, not asserted: what matters is that the answer is a refusal.
    through_gateway = exe.ax(
        "ssh",
        task,
        "--",
        "python3",
        "-c",
        REACH,
        "api.ate-system.svc",
        *api_pod_ips(exe),
        timeout=60,
    )
    exe.measure(
        "control_api_auth", task=task, auth=out.strip(), reach=through_gateway.strip()
    )
    assert "grpc-status: 16" in out, out
    assert "NO SECRETS" in out, out


@needs_policy_state
def test_a_pod_in_the_atespace_reaches_the_api_only_without_the_policy(
    exe: Exe, task: str
) -> None:
    name = f"e2e-api-probe-{secrets.token_hex(3)}"
    targets = ["api.ate-system.svc", *api_pod_ips(exe)]
    overrides = {"spec": {"automountServiceAccountToken": False}}
    exe.kubectl(
        "-n",
        "exe",
        "run",
        name,
        f"--image={exe.image}",
        "--restart=Never",
        f"--overrides={json.dumps(overrides)}",
        "--command",
        "--",
        "python3",
        "-c",
        REACH,
        *targets,
    )
    try:
        exe.wait_until(
            f"probe pod {name} finished",
            lambda: (
                exe.kubectl(
                    "-n", "exe", "get", "pod", name, "-o", "jsonpath={.status.phase}"
                )
                in ("Succeeded", "Failed")
            ),
            timeout=300,
        )
        out = exe.kubectl("-n", "exe", "logs", name)
    finally:
        exe.kubectl("-n", "exe", "delete", "pod", name, "--wait=false", check=False)
    exe.measure(
        "control_api_pod_reach", policy=POLICY, targets=targets, output=out.strip()
    )
    if POLICY == "absent":
        assert answered(out), (
            f"nothing answered without the policy, so the probe proves nothing:\n{out}"
        )
    else:
        assert answered(out) == [], out


@pytest.mark.skipif(POLICY != "present", reason="only once the policy is applied")
def test_the_callers_still_work_behind_the_policy(exe: Exe, task: str) -> None:
    since = utcnow()
    # an L1 tick still reads Substrate
    exe.wait_until(
        f"an L1 decision since {stamp(since)}",
        lambda: exe.l1_decisions(since),
        timeout=300,
        interval=20,
    )
    # and the ax-controller still suspends and resumes through the API
    exe.ax("suspend", "task", task)
    exe.wait_phase(task, "Suspended", timeout=300)
    exe.ax("resume", "task", task)
    exe.wait_phase(task, "Running", timeout=600)
    assert "ok" in exe.ssh(task, "echo ok")
