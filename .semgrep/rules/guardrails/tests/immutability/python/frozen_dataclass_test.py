from dataclasses import dataclass, replace

# ruleid: immutability.prefer-frozen-dataclass-python
@dataclass
class MutableUser:
    name: str
    age: int

# ok: immutability.prefer-frozen-dataclass-python
@dataclass(frozen=True)
class ImmutableUser:
    name: str
    age: int
