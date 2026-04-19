"""
either.py — Either / Result monad for Python scripts.

Mirrors the contract of src/lib/either.ts:

    result: Either[str, Config] = parse_config(path)
    if isinstance(result, Left):
        log.error(result.error)      # "FILE_NOT_FOUND" | "PARSE_ERROR" — type-safe
        return use_defaults()
    start_app(result.value)          # Config — narrowed to Right, type-safe

Note: use isinstance(result, Left) / isinstance(result, Right) for type narrowing.
isLeft() / isRight() return Literal[True/False] but do NOT trigger mypy/pyright
narrowing on union types — isinstance is the correct pattern.

Factory functions:
    right(value)  →  Right[T]
    left(error)   →  Left[E]
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

L = TypeVar("L")
R = TypeVar("R")
U = TypeVar("U")


@dataclass(frozen=True)
class Right(Generic[R]):
    _tag: Literal["Right"] = "Right"
    value: R = None  # type: ignore[assignment]

    def __init__(self, value: R) -> None:
        object.__setattr__(self, "_tag", "Right")
        object.__setattr__(self, "value", value)

    def map(self, mapper: Callable[[R], U]) -> Right[U]:
        return Right(mapper(self.value))

    def flat_map(self, mapper: Callable[[R], Either[L, U]]) -> Either[L, U]:
        return mapper(self.value)

    def fold(self, on_left: Callable[[L], U], on_right: Callable[[R], U]) -> U:
        return on_right(self.value)

    def isRight(self) -> Literal[True]:  # noqa: N802
        return True

    def isLeft(self) -> Literal[False]:  # noqa: N802
        return False


@dataclass(frozen=True)
class Left(Generic[L]):
    _tag: Literal["Left"] = "Left"
    error: L = None  # type: ignore[assignment]

    def __init__(self, error: L) -> None:
        object.__setattr__(self, "_tag", "Left")
        object.__setattr__(self, "error", error)

    def map(self, mapper: Callable[[R], U]) -> Left[L]:
        return self

    def flat_map(self, mapper: Callable[[R], Either[L, U]]) -> Left[L]:
        return self

    def fold(self, on_left: Callable[[L], U], on_right: Callable[[R], U]) -> U:
        return on_left(self.error)

    def isRight(self) -> Literal[False]:  # noqa: N802
        return False

    def isLeft(self) -> Literal[True]:  # noqa: N802
        return True


Either = Left[L] | Right[R]


def right(value: R) -> Right[R]:
    return Right(value)


def left(error: L) -> Left[L]:
    return Left(error)
