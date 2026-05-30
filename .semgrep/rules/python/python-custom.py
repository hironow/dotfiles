# Test fixture for python-custom.yaml (run via `just semgrep-test`).
# Each construct is preceded by a semgrep annotation on the line directly above:
# a ruleid annotation marks an expected match, an ok annotation an expected
# non-match. Cases are kept isolated so each rule fires only where annotated.
# Names left undefined on purpose — semgrep matches syntactically, not at runtime.


# --- python-forbid-ambiguous-class-name ---
# ruleid: python-forbid-ambiguous-class-name
class UserManager:
    pass


# ok: python-forbid-ambiguous-class-name
class UserSession:
    pass


# --- python-forbid-protocol ---
# ruleid: python-forbid-protocol
from typing import Protocol


# --- python-no-typing-any ---
# ruleid: python-no-typing-any
from typing import Any


# --- python-no-import-star ---
# ruleid: python-no-import-star
from os import *


# --- python-no-httpx ---
# ruleid: python-no-httpx
import httpx


# --- python-no-requests ---
# ruleid: python-no-requests
import requests


# --- use-loguru-instead-of-logging ---
# ruleid: use-loguru-instead-of-logging
import logging


# --- python-no-pickle ---
# ruleid: python-no-pickle
import pickle


# --- python-no-pdb ---
# ruleid: python-no-pdb
import pdb


# --- python-unnecessary-future-annotations ---
# ruleid: python-unnecessary-future-annotations
from __future__ import annotations


# --- no-print ---
# ruleid: no-print
print("hello")


# --- no-eval ---
# ruleid: no-eval
eval("1 + 1")


# --- python-no-exec ---
# ruleid: python-no-exec
exec("x = 1")


# --- python-naive-datetime ---
# ruleid: python-naive-datetime
naive = datetime.now()
# ruleid: python-naive-datetime
naive_utc = datetime.utcnow()


# --- python-avoid-dict-keys-iteration ---
# ruleid: python-avoid-dict-keys-iteration
for k in d.keys():
    pass


# ok: python-avoid-dict-keys-iteration
for k in d:
    pass


# --- python-avoid-dict-keys-membership ---
# ruleid: python-avoid-dict-keys-membership
if key in d.keys():
    pass


# --- python-avoid-range-len ---
# ruleid: python-avoid-range-len
for i in range(len(items)):
    pass


# ok: python-avoid-range-len
for idx, item in enumerate(items):
    pass


# --- python-open-without-with ---
# ruleid: python-open-without-with
fh = open("file.txt")


# ok: python-open-without-with
with open("file.txt") as managed:
    pass


# --- use-pathlib-instead-of-os-path ---
# ruleid: use-pathlib-instead-of-os-path
joined = os.path.join("a", "b")


# --- python-yaml-unsafe-load ---
# ruleid: python-yaml-unsafe-load
loaded = yaml.load(text)


# ok: python-yaml-unsafe-load
loaded_safe = yaml.safe_load(text)


# --- python-subprocess-shell-true ---
# ruleid: python-subprocess-shell-true
subprocess.run("ls", shell=True)
# ruleid: python-subprocess-shell-true
os.system("ls")


# ok: python-subprocess-shell-true
subprocess.run(["ls", "-l"])


# --- python-no-mutable-default-args ---
# ruleid: python-no-mutable-default-args
def with_mutable_default(items=[]):
    return items


# ok: python-no-mutable-default-args
def without_mutable_default(items=None):
    return items


# --- python-raise-bare-exception ---
def raises_bare():
    # ruleid: python-raise-bare-exception
    raise Exception("too broad")


# ok: python-raise-bare-exception
def raises_specific():
    raise ValueError("specific")


# --- python-async-no-time-sleep & python-asyncio-sleep-requires-await ---
async def async_worker():
    # ruleid: python-async-no-time-sleep
    time.sleep(1)
    # ruleid: python-asyncio-sleep-requires-await
    asyncio.sleep(1)
    # ok: python-asyncio-sleep-requires-await
    await asyncio.sleep(1)


# --- python-forbid-multi-level-inheritance ---
class GrandParent:
    pass


# ruleid: python-forbid-multi-level-inheritance
class Parent(GrandParent):
    pass


class Child(Parent):
    pass
