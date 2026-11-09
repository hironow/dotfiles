"""Which Firebase emulators the stack runs, asked from the emulator itself.

firebase-tools starts the Functions, Eventarc, and Tasks emulators only when
Functions or Extensions are configured (src/emulator/controller.ts,
`if (emulatableBackends.length)`). firebase/firebase.json configures neither,
so this stack does not provide those three. The Emulator UI's /api/config
lists the emulators that are running.
"""

import json

import pytest
from aiohttp import ClientTimeout

from tests.utils.helpers import host_endpoint

PROVIDED = ("auth", "firestore", "pubsub", "storage")
NOT_PROVIDED = ("eventarc", "functions", "tasks")


def emulator_listing_problems(status: int, body: str) -> list[str]:
    """What is wrong with an /api/config answer; empty when the stack runs
    every emulator it provides and none it does not."""
    if status != 200:
        return [f"Emulator UI /api/config answered HTTP {status}"]
    try:
        config = json.loads(body)
    except json.JSONDecodeError:
        return ["Emulator UI /api/config is not JSON"]
    if not isinstance(config, dict):
        return ["Emulator UI /api/config is not a JSON object"]
    # each running emulator is an entry with its listen address
    running = {
        name
        for name, info in config.items()
        if isinstance(info, dict) and "host" in info and "port" in info
    }
    problems = [f"not running: {name}" for name in PROVIDED if name not in running]
    problems += [
        f"running but not provided (update README and tests): {name}"
        for name in NOT_PROVIDED
        if name in running
    ]
    return problems


def _listing(*names):
    # projectId, experiments, and analytics sit beside the emulators; only an
    # entry with a listen address is a running emulator
    return json.dumps(
        {"projectId": "test-project", "experiments": [], "analytics": {"id": "x"}}
        | {name: {"name": name, "host": "0.0.0.0", "port": 1} for name in names}
    )


def test_an_entry_without_a_listen_address_is_not_a_running_emulator():
    listing = json.loads(_listing("hub", "ui", *PROVIDED))
    listing["functions"] = {"name": "functions"}
    assert emulator_listing_problems(200, json.dumps(listing)) == []


def test_the_provided_emulators_and_no_others_pass():
    assert emulator_listing_problems(200, _listing("hub", "ui", *PROVIDED)) == []


@pytest.mark.parametrize("missing", PROVIDED)
def test_a_provided_emulator_not_running_is_a_problem(missing):
    running = [name for name in PROVIDED if name != missing]
    problems = emulator_listing_problems(200, _listing("hub", "ui", *running))
    assert problems == [f"not running: {missing}"]


@pytest.mark.parametrize("extra", NOT_PROVIDED)
def test_an_emulator_the_stack_does_not_provide_is_a_problem(extra):
    problems = emulator_listing_problems(200, _listing(*PROVIDED, extra))
    assert problems == [f"running but not provided (update README and tests): {extra}"]


@pytest.mark.parametrize(
    "status,body,problem",
    [
        (503, _listing(*PROVIDED), "Emulator UI /api/config answered HTTP 503"),
        (200, "<html></html>", "Emulator UI /api/config is not JSON"),
        (200, "[]", "Emulator UI /api/config is not a JSON object"),
    ],
    ids=["http-503", "not-json", "json-array"],
)
def test_an_answer_that_is_not_a_listing_is_a_problem(status, body, problem):
    assert emulator_listing_problems(status, body) == [problem]


@pytest.mark.asyncio
async def test_firebase_runs_the_provided_emulators_only(http_client):
    url = host_endpoint("http://localhost:4000/api/config")
    async with http_client.get(url, timeout=ClientTimeout(total=5.0)) as response:
        status, body = response.status, await response.text()
    assert emulator_listing_problems(status, body) == [], body
