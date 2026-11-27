"""Run the real tailnet module against loopback GCS and Tailscale services."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

import pytest

ROOT = Path(__file__).resolve().parents[2]
REQUIRE_ENV = "DOTFILES_REQUIRE_TAILNET_SCENARIOS"


def _tailnet_inputs() -> dict[str, str]:
    source = ROOT / "tofu/tailnet"
    inputs = {p.name: p.read_text(encoding="utf-8") for p in source.glob("*.tf")}
    for name in ("acl.hujson", ".terraform.lock.hcl"):
        inputs[name] = (source / name).read_text(encoding="utf-8")
    return inputs


def _process_env() -> dict[str, str]:
    return {k: os.environ[k] for k in ("PATH", "SystemRoot") if k in os.environ}


def _unavailable(reason: str) -> NoReturn:
    if os.environ.get(REQUIRE_ENV) == "1":
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture(scope="session")
def tailnet_tools(tmp_path_factory):
    tofu = shutil.which("tofu")
    if tofu is None:
        _unavailable("tailnet scenarios need the installed OpenTofu executable")
    root = tmp_path_factory.mktemp("tailnet-provider")
    source = root / "source"
    source.mkdir()
    for name, value in _tailnet_inputs().items():
        (source / name).write_text(value, encoding="utf-8")
    config = root / "init.tfrc"
    config.write_text("disable_checkpoint = true\n", encoding="utf-8")
    env = dict(_process_env(), HOME=str(root), TF_CLI_CONFIG_FILE=str(config))
    cache = os.environ.get("TF_PLUGIN_CACHE_DIR")
    if cache:
        env["TF_PLUGIN_CACHE_DIR"] = cache
    done = subprocess.run(
        [tofu, "init", "-backend=false", "-input=false", "-lockfile=readonly"],
        cwd=source,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=90,
    )
    if done.returncode:
        _unavailable("tailnet provider init failed:\n" + done.stdout + done.stderr)
    # Init obtains the real locked provider through the job's cache or registry.
    # All scenario inits use only this unpacked mirror, without registry access.
    mirror = source / ".terraform/providers"
    config = root / "offline.tfrc"
    config.write_text(
        "disable_checkpoint = true\nprovider_installation {\n"
        f'  filesystem_mirror {{ path = "{mirror.as_posix()}" }}\n}}\n',
        encoding="utf-8",
    )
    return tofu, config


_TAILNET_HTTP = r"""
import base64
import email.parser
import email.policy
import hashlib
import http.server
import json
import pathlib
import re
import subprocess
import threading
import urllib.parse


class Services(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, value, raw=False):
        data = value if raw else json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/octet-stream" if raw else "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("ETag", '"fixture-policy"')
        if raw:
            self.send_header("x-goog-generation", "1")
            self.send_header("Last-Modified", "Wed, 25 Nov 2026 00:00:00 GMT")
        self.end_headers()
        self.wfile.write(data)

    def read_body(self):
        if self.headers.get("Transfer-Encoding", "").lower() != "chunked":
            return self.rfile.read(int(self.headers.get("Content-Length", "0")))
        chunks = []
        while True:
            size = int(self.rfile.readline().split(b";", 1)[0], 16)
            if size == 0:
                while self.rfile.readline() not in (b"\r\n", b""):
                    pass
                return b"".join(chunks)
            chunk = self.rfile.read(size)
            if len(chunk) != size or self.rfile.read(2) != b"\r\n":
                raise ValueError("invalid chunked upload")
            chunks.append(chunk)

    def handle_request(self):
        url = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(url.query)
        body = self.read_body()
        requests.append((self.command, self.path))
        if "kmsKeyName" in query or any("encryption" in k.lower() for k in self.headers):
            violations.append("tailnet guard:backend-kms: " + self.path)
            return self.reply(400, {"error": {"code": 400, "message": "tailnet guard:backend-kms"}})
        if url.path.startswith("/api/v2/tailnet/fixture.test/acl"):
            if self.command == "GET" and url.path.endswith("/acl"):
                return self.reply(200, expected_acl.encode(), raw=True)
            if self.command == "POST" and url.path.endswith("/acl/validate"):
                return self.reply(200, {})
            violations.append(self.path)
            return self.reply(405, {})
        match = re.fullmatch(r"/(?:upload/)?storage/v1/b/([^/]+)/o(?:/(.*))?", url.path)
        if match is None:
            # The storage client's reader uses the XML download endpoint.
            download = re.fullmatch(r"/([^/]+)/(.*)", url.path)
            if self.command == "GET" and download is not None:
                key = tuple(urllib.parse.unquote(p) for p in download.groups())
                if key == state_key and key in objects:
                    return self.reply(200, objects[key], raw=True)
                if key[0] != state_key[0] or not key[1].startswith("tailnet/"):
                    violations.append("tailnet guard:state-location: " + self.path)
            violations.append(self.path)
            return self.reply(404, {"error": {"code": 404, "message": "unknown endpoint"}})
        bucket, name = match.groups()
        name = urllib.parse.unquote(name) if name is not None else query.get("name", [""])[0]
        key = (urllib.parse.unquote(bucket), name)
        location = name or query.get("prefix", [""])[0]
        if key[0] != state_key[0] or (location and not location.startswith("tailnet/")):
            violations.append("tailnet guard:state-location: " + self.path)
            return self.reply(404, {"error": {"code": 404, "message": "tailnet guard:state-location"}})
        def metadata(k):
            digest = base64.b64encode(hashlib.md5(objects[k], usedforsecurity=False).digest()).decode()
            return {"kind": "storage#object", "bucket": k[0], "name": k[1], "generation": "1", "size": str(len(objects[k])), "md5Hash": digest}
        if self.command == "GET" and not name:
            prefix = query.get("prefix", [""])[0]
            return self.reply(200, {"kind": "storage#objects", "items": [metadata(k) for k in objects if k[0] == key[0] and k[1].startswith(prefix)]})
        if self.command == "GET":
            if key not in objects:
                return self.reply(404, {"error": {"code": 404, "message": "not found"}})
            if query.get("alt") == ["media"]:
                return self.reply(200, objects[key], raw=True)
            return self.reply(200, metadata(key))
        if self.command == "DELETE":
            objects.pop(key, None)
            return self.reply(204, b"", raw=True)
        if self.command == "POST" and query.get("uploadType") == ["multipart"]:
            message = email.parser.BytesParser(policy=email.policy.default).parsebytes(
                ("Content-Type: " + self.headers["Content-Type"] + "\r\n\r\n").encode() + body
            )
            parts = list(message.iter_parts())
            meta = json.loads(parts[0].get_payload(decode=True))
            key = (key[0], meta["name"])
            if meta.get("kmsKeyName"):
                violations.append("tailnet guard:backend-kms: " + self.path)
                return self.reply(400, {"error": {"code": 400, "message": "tailnet guard:backend-kms"}})
            objects[key] = parts[1].get_payload(decode=True)
            return self.reply(200, metadata(key))
        violations.append(self.path)
        return self.reply(400, {"error": {"code": 400, "message": "unsupported GCS request"}})

    do_GET = do_POST = do_DELETE = handle_request
"""


_TAILNET_ENCRYPTION = r"""
def assert_encrypted_state(raw, state):
    assert state["outputs"]["confidential"]["value"].encode() not in raw
    assert b"fixture-passphrase" not in raw
    assert json.loads(raw).get("encrypted_data"), raw[:200]


def write_local_backend_override(probe):
    (probe / "backend_override.tf").write_text('terraform {\n  backend "local" {}\n}\n', encoding="utf-8")
"""


_TAILNET_RUNTIME = (
    _TAILNET_HTTP
    + _TAILNET_ENCRYPTION
    + r"""
root = pathlib.Path(RUNTIME_ROOT)
stack = root / "stack"
stack.mkdir()
for name, value in INPUTS.items():
    (stack / name).write_text(value, encoding="utf-8")
expected_acl = INPUTS["acl.hujson"]
state_key = ("gen-ai-hironow-tofu-state", "tailnet/default.tfstate")
objects = {}
requests = []
violations = []
lineage = "0ea236f7-40bc-4f81-9ec5-8be1094de25a"
confidential = "synthetic-confidential-state-output"

server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Services)
threading.Thread(target=server.serve_forever, daemon=True).start()
endpoint = "http://127.0.0.1:" + str(server.server_port)
env = {
    **PROCESS_ENV,
    "HOME": str(root),
    "TF_CLI_CONFIG_FILE": TFRC,
    "TF_IN_AUTOMATION": "1",
    "CHECKPOINT_DISABLE": "1",
    "HTTP_PROXY": endpoint,
    "HTTPS_PROXY": endpoint,
    "ALL_PROXY": endpoint,
    "NO_PROXY": "127.0.0.1,localhost,::1",
    "GOOGLE_APPLICATION_CREDENTIALS": str(root / "absent-credentials.json"),
    "GOOGLE_BACKEND_STORAGE_CUSTOM_ENDPOINT": endpoint + "/storage/v1/",
    "TAILSCALE_API_KEY": "synthetic-api-key",
    "TAILSCALE_BASE_URL": endpoint,
    "TF_VAR_tailnet": "fixture.test",
    # Override only the key. Source method and enforcement flags stay in force.
    "TF_ENCRYPTION": 'key_provider "pbkdf2" "default" { passphrase = "fixture-passphrase-with-no-private-key" }',
}

def run(*args, directory=stack, changes=None, ok=True):
    done = subprocess.run(
        [TOFU, *args], cwd=directory, env=dict(env, **(changes or {})),
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
        check=False,
    )
    if ok:
        assert done.returncode == 0, done.stdout + done.stderr + repr(violations)
    return done

tofu_version = json.loads(run("version", "-json").stdout)["terraform_version"]
# Seed from a separate module and a fixed location, never the tested backend.
seed = root / "seed"
seed.mkdir()
(seed / "main.tf").write_text('''
terraform {
  encryption {
    key_provider "pbkdf2" "default" {
      passphrase = "fixture-passphrase-with-no-private-key"
    }
    method "aes_gcm" "default" {
      keys = key_provider.pbkdf2.default
    }
    state {
      method = method.aes_gcm.default
      enforced = true
    }
  }
}
''', encoding="utf-8")
state = {
    "version": 4, "terraform_version": tofu_version, "serial": 1, "lineage": lineage,
    "outputs": {"confidential": {"value": confidential, "type": "string", "sensitive": True}},
    "resources": [],
}
if SCENARIO != "import":
    state["resources"] = [{
        "mode": "managed", "type": "tailscale_acl", "name": "this",
        "provider": 'provider["registry.opentofu.org/tailscale/tailscale"]',
        "instances": [{"schema_version": 0, "attributes": {
            "id": "acl", "acl": expected_acl, "overwrite_existing_content": True,
            "reset_acl_on_destroy": None,
        }, "sensitive_attributes": []}],
    }]
(seed / "seed.json").write_text(json.dumps(state), encoding="utf-8")
run("init", "-input=false", directory=seed)
run("state", "push", "-force", "-lock=false", "seed.json", directory=seed)
objects[state_key] = (seed / "terraform.tfstate").read_bytes()
# Give only the GCS backend a token; a KMS dependency must find no credentials.
run("init", "-input=false", "-lockfile=readonly", "-backend-config=access_token=synthetic-token")
pulled = json.loads(run("state", "pull").stdout)
assert pulled["lineage"] == lineage, pulled
assert pulled["outputs"]["confidential"]["value"] == confidential, pulled

if SCENARIO in ("private", "backend", "encryption"):
    original_ciphertext = objects[state_key]
    # Change the state so the backend cannot optimize this push into a no-op.
    pulled["serial"] += 1
    pulled["outputs"]["confidential"]["value"] = confidential + "-roundtrip"
    (stack / "roundtrip.json").write_text(json.dumps(pulled), encoding="utf-8")
    run("state", "push", "-force", "-lock=false", "roundtrip.json")
    roundtrip = json.loads(run("state", "pull").stdout)
    assert roundtrip["lineage"] == lineage
    assert roundtrip["outputs"]["confidential"]["value"] == confidential + "-roundtrip"
    raw = objects[state_key]
    assert raw != original_ciphertext, "state push did not upload changed ciphertext"
    assert_encrypted_state(raw, pulled)

if SCENARIO in ("import", "destroy", "encryption"):
    run("plan", "-input=false", "-lock=false", "-out=normal.tfplan")
    plan = json.loads(run("show", "-json", "normal.tfplan").stdout)
    changes = [c for c in plan["resource_changes"] if c["address"] == "tailscale_acl.this"]
    assert len(changes) == 1, plan
    change = changes[0]
    assert change["change"]["after"]["acl"] == expected_acl, "tailnet guard:planned-acl: " + repr(change)
    if SCENARIO == "import":
        assert change["change"].get("importing", {}).get("id") == "acl", "tailnet guard:live-import: " + repr(change)
        assert "create" not in change["change"]["actions"], change
    if SCENARIO == "destroy":
        denied = run("plan", "-destroy", "-input=false", "-lock=false", ok=False)
        assert denied.returncode != 0, "tailnet guard:prevent-destroy: " + denied.stdout
        assert "prevent_destroy" in denied.stderr and "tailscale_acl.this" in denied.stderr, denied.stderr
    if SCENARIO == "encryption":
        wrong = {"TF_ENCRYPTION": 'key_provider "pbkdf2" "default" { passphrase = "a-different-passphrase-for-negative-proof" }'}
        for args in (("state", "pull"), ("show", "-json", "normal.tfplan")):
            denied = run(*args, changes=wrong, ok=False)
            assert denied.returncode != 0, denied.stdout
            assert "decrypt" in (denied.stdout + denied.stderr).lower(), denied.stderr
        # Empty local backends prevent old ciphertext from causing false refusals.
        for section in ("state", "plan"):
            probe = root / section
            probe.mkdir()
            for path in stack.glob("*.tf"):
                (probe / path.name).write_bytes(path.read_bytes())
            (probe / "acl.hujson").write_text(expected_acl, encoding="utf-8")
            (probe / ".terraform.lock.hcl").write_bytes((stack / ".terraform.lock.hcl").read_bytes())
            write_local_backend_override(probe)
            run("init", "-input=false", "-lockfile=readonly", directory=probe)
            override = env["TF_ENCRYPTION"] + '\nmethod "unencrypted" "probe" {}\n' + section + ' { method = method.unencrypted.probe }'
            denied = run("plan", "-input=false", "-lock=false", "-out=probe.tfplan", directory=probe, changes={"TF_ENCRYPTION": override}, ok=False)
            assert denied.returncode != 0, "tailnet guard:" + section + "-enforcement: allowed unencrypted output"
            assert "enforced" in (denied.stdout + denied.stderr).lower(), denied.stderr

assert requests, "no fake service was reached"
assert not violations, violations
assert any("/o/" in path for _, path in requests), requests
server.shutdown()
print("tailnet scenario passed: " + SCENARIO)
"""
)


def _tailnet_run(
    tools, scenario: str, root: Path, inputs=None
) -> subprocess.CompletedProcess:
    tofu, config = tools
    if inputs is None:
        inputs = _tailnet_inputs()
    program = (
        f"INPUTS = {inputs!r}\nSCENARIO = {scenario!r}\n"
        f"TOFU = {tofu!r}\nTFRC = {str(config)!r}\n"
        f"RUNTIME_ROOT = {str(root)!r}\nPROCESS_ENV = {_process_env()!r}\n"
        + _TAILNET_RUNTIME
    )
    return subprocess.run(
        [sys.executable, "-c", program],
        env=_process_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=90,
    )


def _assert_scenario(tools, scenario: str, root: Path) -> None:
    result = _tailnet_run(tools, scenario, root)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"tailnet scenario passed: {scenario}" in result.stdout


def test_tailnet_state_works_without_private_kms(tailnet_tools, tmp_path):
    _assert_scenario(tailnet_tools, "private", tmp_path)


def test_tailnet_backend_reads_the_existing_state(tailnet_tools, tmp_path):
    _assert_scenario(tailnet_tools, "backend", tmp_path)


def test_tailnet_state_and_plan_encryption_are_enforced(tailnet_tools, tmp_path):
    _assert_scenario(tailnet_tools, "encryption", tmp_path)


def test_tailnet_plan_imports_the_existing_acl(tailnet_tools, tmp_path):
    _assert_scenario(tailnet_tools, "import", tmp_path)


def test_tailnet_destroy_plan_is_refused(tailnet_tools, tmp_path):
    _assert_scenario(tailnet_tools, "destroy", tmp_path)
