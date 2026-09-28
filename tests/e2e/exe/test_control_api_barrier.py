"""Plan F5 from inside a task: what stands between a task and the Control API.

L1's drain barrier (plan D2) holds only if nothing but the components it stops
can resume an actor. Substrate's Control API authenticates its callers but does
not authorize them (plan F1). W2 found that its network half does not hold:
from inside a task, api.ate-system.svc resolves and answers a TLS handshake.
Two layers can still hold, and this module tests each:

- authentication. The API admits only a Kubernetes SA token for audience
  api.ate-system.svc, or a client certificate from the pod-identity CA. A
  guest has neither, so an unauthenticated call is refused with
  UNAUTHENTICATED, and the guest has no /var/run/secrets at all.
- the network. tofu/exe-cluster/control_api.tf admits the API's port only from
  its callers, and the atespace's worker pods are not among them, so once it
  is applied nothing answers the task, by name or at the pods' own addresses.

W3 runs `-k authenticate` before the policy is applied and the whole module
after. It needs only a node and one task, and leaves 0 nodes like the rest.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from exe_live import Exe

# A TLS handshake with the Control API at each target, with verification on.
# The task does not trust the cluster's CA, so a server that answers fails
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


def test_a_task_cannot_authenticate_to_the_control_api(exe: Exe, task: str) -> None:
    out = exe.ax("ssh", task, "--", "sh", "-c", AUTH, timeout=60)
    exe.measure("control_api_auth_probe", task=task, output=out.strip())
    assert "grpc-status: 16" in out, out
    assert "NO SECRETS" in out, out


def test_a_task_cannot_reach_the_control_api(exe: Exe, task: str) -> None:
    ips = api_pod_ips(exe)
    assert ips, "no endpoint for Service ate-system/api"
    out = exe.ax(
        "ssh",
        task,
        "--",
        "python3",
        "-c",
        REACH,
        "api.ate-system.svc",
        *ips,
        timeout=60,
    )
    exe.measure(
        "control_api_reach_probe",
        task=task,
        targets=["api.ate-system.svc", *ips],
        output=out.strip(),
    )
    assert out.strip().splitlines()[-1] == "ANSWERED", out
