"""hapi-parity response helpers (interface stub; implementation follows)."""

from __future__ import annotations

from typing import Any


class _Undefined:
    def __repr__(self) -> str:
        return "UNDEFINED"


UNDEFINED: Any = _Undefined()


def js_string(value: object) -> str:
    return ""
