"""Helper functions for tests using the Result type."""

import asyncio
import socket
import time


import docker
from aiohttp import ClientSession
from docker.errors import NotFound

from docker.models.containers import Container

from tests.utils.result import Error, Ok, Result


def get_container(client: docker.DockerClient, name: str) -> Result[Container, str]:
    """Get a container by name."""
    try:
        container = client.containers.get(name)
        return Ok(container)
    except NotFound:
        return Error(f"Container '{name}' not found.")
    except Exception as e:
        return Error(f"Error getting container '{name}': {e}")


async def wait_for_http(
    client: ClientSession, url: str, retries: int = 30
) -> Result[bool, str]:
    """Wait for an HTTP endpoint to be available."""
    last_error = ""
    for _ in range(retries):
        try:
            async with client.get(url) as response:
                if response.status == 200:
                    return Ok(True)
                last_error = f"Status {response.status}"
        except Exception as e:
            last_error = str(e)
        await asyncio.sleep(1)
    return Error(f"HTTP endpoint {url} not accessible: {last_error}")


def wait_for_tcp(host: str, port: int, retries: int = 30) -> Result[bool, str]:
    """Wait for a TCP port to be open (synchronous)."""
    last_error = ""
    for _ in range(retries):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return Ok(True)
            last_error = f"Connect result: {result}"
        except Exception as e:
            last_error = str(e)
        time.sleep(1)
    return Error(f"TCP endpoint {host}:{port} not accessible: {last_error}")
