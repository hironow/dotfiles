"""Real native resolvers, owned packages, loopback registry, no external installs.

Baseline/top-only/zero/removal/timestamp-only controls attribute failure to age,
not to a broken registry. No fixture CLI is executed and no interpreter downloaded.
"""

import base64
import csv
import datetime as dt
import hashlib
import http.server
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import threading
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLI = "dotfiles-age-cli"
DEP = "dotfiles-age-dep"


def npm_archive(name: str, dependency: bool) -> bytes:
    metadata = {"name": name, "version": "1.0.0"}
    if dependency:
        metadata["dependencies"] = {DEP: "^1.0.0"}
        metadata["bin"] = {CLI: "cli.js"}
    body = json.dumps(metadata).encode()
    result = io.BytesIO()
    with tarfile.open(fileobj=result, mode="w:gz", encoding="utf-8") as archive:
        entry = tarfile.TarInfo("package/package.json")
        entry.size = len(body)
        entry.mode = 0o644
        archive.addfile(entry, io.BytesIO(body))
        if dependency:
            marker = b'#!/usr/bin/env bun\nconsole.log("owned fixture");\n'
            entry = tarfile.TarInfo("package/cli.js")
            entry.size = len(marker)
            entry.mode = 0o755
            archive.addfile(entry, io.BytesIO(marker))
    return result.getvalue()


def python_wheel(name: str, dependency: bool) -> bytes:
    module = name.replace("-", "_")
    dist = module + "-1.0.0.dist-info"
    metadata = f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0.0\n"
    if dependency:
        metadata += f"Requires-Dist: {DEP}>=1.0.0,<2.0.0\n"
    files = {
        module + "/__init__.py": b'VALUE = "owned fixture"\n',
        dist + "/METADATA": (metadata + "\n").encode(),
        dist
        + "/WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    if dependency:
        files[module + "/cli.py"] = b'def main():\n    print("owned fixture")\n'
        files[dist + "/entry_points.txt"] = (
            f"[console_scripts]\n{CLI} = {module}.cli:main\n".encode()
        )
    rows = []
    for path, body in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(body).digest()).rstrip(b"=")
        rows.append([path, "sha256=" + digest.decode(), str(len(body))])
    rows.append([dist + "/RECORD", "", ""])
    record = io.StringIO()
    csv.writer(record, lineterminator="\n").writerows(rows)
    files[dist + "/RECORD"] = record.getvalue().encode()
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        for path, body in files.items():
            archive.writestr(path, body)
    return result.getvalue()


def native_binary(name: str) -> Path:
    found = shutil.which(name)
    if not found or "shims" in Path(found).parts:
        pytest.skip(f"native {name} unavailable (do not bootstrap or invoke shims)")
    binary = Path(found).resolve()
    with binary.open("rb") as stream:
        magic = stream.read(4)
    if magic not in {
        b"\x7fELF",
        b"\xcf\xfa\xed\xfe",
        b"\xfe\xed\xfa\xcf",
        b"\xca\xfe\xba\xbe",
    } and not magic.startswith(b"MZ"):
        pytest.skip(f"{name} resolves to a script rather than a reviewed native binary")
    if binary.name in {"mise", "mise.exe"}:
        pytest.skip(f"{name} resolves to the mise dispatcher")
    return binary


@pytest.mark.parametrize("manager", ["bun", "uv"])
def test_dedicated_cli_dependencies_bypass_age_only_with_scoped_override(
    tmp_path: Path, manager: str
) -> None:
    binary = native_binary(manager)
    cfg = tomllib.loads((ROOT / "config/mise/config.toml").read_text(encoding="utf-8"))
    if manager == "bun":
        zero = shlex.split(cfg["tools"]["vp"]["bun_args"])
    else:
        args = shlex.split(cfg["tools"]["pypi:headroom-ai"]["uvx_args"])
        assert args[:2] == ["--python", "3.13"]
        zero = args[2:]  # use this test's existing interpreter, never download 3.13
    now = dt.datetime.now(dt.UTC)
    old = (now - dt.timedelta(days=14)).isoformat().replace("+00:00", "Z")
    young = (now - dt.timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    state = {"old_dependency": False}
    assets: dict[str, bytes] = {}
    for name in (CLI, DEP):
        assets[f"/files/{name}.tgz"] = npm_archive(name, name == CLI)
        filename = name.replace("-", "_") + "-1.0.0-py3-none-any.whl"
        assets["/files/" + filename] = python_wheel(name, name == CLI)

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *_args: object) -> None:
            pass

        def do_HEAD(self) -> None:
            path = self.path.split("?", 1)[0]
            if path not in assets:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(assets[path])))
            self.end_headers()

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path in assets:
                body, content_type = assets[path], "application/octet-stream"
            elif path.startswith("/npm/"):
                name = path.removeprefix("/npm/").strip("/")
                if name not in (CLI, DEP):
                    self.send_error(404)
                    return
                target = "/files/" + name + ".tgz"
                version = {
                    "name": name,
                    "version": "1.0.0",
                    "dist": {
                        "tarball": base + target,
                        "shasum": hashlib.sha1(assets[target]).hexdigest(),
                    },
                }
                if name == CLI:
                    version["dependencies"] = {DEP: "^1.0.0"}
                    version["bin"] = {CLI: "cli.js"}
                published = old if name == CLI or state["old_dependency"] else young
                body = json.dumps(
                    {
                        "name": name,
                        "dist-tags": {"latest": "1.0.0"},
                        "versions": {"1.0.0": version},
                        "time": {
                            "created": old,
                            "modified": published,
                            "1.0.0": published,
                        },
                    }
                ).encode()
                content_type = "application/json"
            elif path.startswith("/pypi/"):
                name = path.removeprefix("/pypi/").strip("/")
                if name not in (CLI, DEP):
                    self.send_error(404)
                    return
                filename = name.replace("-", "_") + "-1.0.0-py3-none-any.whl"
                target = "/files/" + filename
                published = old if name == CLI or state["old_dependency"] else young
                body = json.dumps(
                    {
                        "meta": {"api-version": "1.4"},
                        "name": name,
                        "files": [
                            {
                                "filename": filename,
                                "url": base + target,
                                "hashes": {
                                    "sha256": hashlib.sha256(assets[target]).hexdigest()
                                },
                                "upload-time": published,
                                "requires-python": ">=3.10",
                                "yanked": False,
                            }
                        ],
                    }
                ).encode()
                content_type = "application/vnd.pypi.simple.v1+json"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    base = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for case, extra, expect_success, old_dependency in [
            ("baseline", [], False, False),
            (
                "top-only",
                ["--minimum-release-age-excludes=" + CLI]
                if manager == "bun"
                else ["--exclude-newer-package", CLI + "=false"],
                False,
                False,
            ),
            ("scoped-zero", zero, True, False),
            ("zero-removed", [], False, False),
            ("timestamp-only-old", [], True, True),
        ]:
            state["old_dependency"] = old_dependency
            home = tmp_path / case
            home.mkdir()
            env = {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "APPDATA": str(home / "appdata"),
                "LOCALAPPDATA": str(home / "localappdata"),
                "XDG_CONFIG_HOME": str(home / "config"),
                "XDG_CACHE_HOME": str(home / "cache"),
                "PATH": os.pathsep.join(
                    [
                        str(binary.parent),
                        str(Path(sys.executable).parent),
                        "/usr/bin",
                        "/bin",
                        "/usr/sbin",
                        "/sbin",
                    ]
                ),
                "CI": "1",
                "NO_COLOR": "1",
                "LC_ALL": "C",
                "BUN_INSTALL_GLOBAL_DIR": str(home / "global"),
                "BUN_INSTALL_BIN": str(home / "bin"),
                "BUN_INSTALL_CACHE_DIR": str(home / "bun-cache"),
                "NPM_CONFIG_REGISTRY": base + "/npm/",
                "UV_TOOL_DIR": str(home / "tools"),
                "UV_TOOL_BIN_DIR": str(home / "bin"),
                "UV_CACHE_DIR": str(home / "uv-cache"),
                "UV_PYTHON_DOWNLOADS": "never",
            }
            if "SYSTEMROOT" in os.environ:
                env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
            if manager == "bun":
                command = [
                    str(binary),
                    "install",
                    CLI + "@1.0.0",
                    "--global",
                    "--linker",
                    "hoisted",
                    "--ignore-scripts",
                    "--minimum-release-age=604800",
                    *extra,
                ]
            else:
                uv_dir = home / "config/uv"
                uv_dir.mkdir(parents=True)
                (uv_dir / "uv.toml").write_text(
                    'exclude-newer = "7 days"\n', encoding="utf-8"
                )
                win_uv = home / "appdata/uv"
                win_uv.mkdir(parents=True)
                (win_uv / "uv.toml").write_text(
                    'exclude-newer = "7 days"\n', encoding="utf-8"
                )
                command = [
                    str(binary),
                    "tool",
                    "install",
                    CLI + "==1.0.0",
                    "--python",
                    sys.executable,
                    "--no-python-downloads",
                    "--no-cache",
                    "--index-url",
                    base + "/pypi/",
                    *extra,
                ]
            result = subprocess.run(
                command,
                cwd=home,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=45,
            )
            assert (result.returncode == 0) == expect_success, (
                manager,
                case,
                result.stdout,
                result.stderr,
            )
            if not expect_success:
                assert (
                    "minimum-release-age" if manager == "bun" else "exclude-newer"
                ) in result.stderr
            elif manager == "bun":
                assert (home / "global/node_modules" / DEP / "package.json").is_file()
            else:
                assert list((home / "tools").rglob("dotfiles_age_dep-1.0.0.dist-info"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
