"""Module containing definitions for the result type.

It works like Rust's Result type.
"""

from dataclasses import dataclass
from typing import Generic, TypeVar

_T = TypeVar("_T")
_E = TypeVar("_E")


@dataclass(frozen=True)
class Ok(Generic[_T]):  # noqa: UP046
    value: _T

    def __repr__(self):
        return f"Ok({self.value!r})"


@dataclass(frozen=True)
class Error(Generic[_E]):  # noqa: UP046
    """Failure representation."""

    value: _E

    def __repr__(self):
        return f"Error({self.value!r})"


# type Result<'Success,'Failure> =
#   | Ok of 'Success
#   | Error of 'Failure
Result = Ok[_T] | Error[_E]
