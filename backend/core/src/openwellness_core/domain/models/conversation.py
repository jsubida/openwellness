"""Conversation domain model."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from .base_owner_entity import BaseOwnerEntity

# pylint: disable=redefined-builtin


@dataclass(kw_only=True)
class Conversation(BaseOwnerEntity):
    """A Conversation is a collection of shared Posts."""

    class Filter:
        """A way to narrow down a set of Conversations."""

        class Type(Enum):
            CHANNELS = auto()
            KIND = auto()
            WEEK = auto()

            def __str__(self) -> str:
                if self == Conversation.Filter.Type.CHANNELS:
                    return "channels"
                elif self == Conversation.Filter.Type.KIND:
                    return "kind"
                elif self == Conversation.Filter.Type.WEEK:
                    return "week"
                else:
                    return "unknown"

        def __init__(self, type: Type, val: Any) -> None:
            self.type = type
            self.val = val

        def n1ql(self) -> str:
            if self.type == Conversation.Filter.Type.CHANNELS:
                channel_list = '","'.join(self.val)
                return f'ANY c in channels SATISFIES c IN ["{channel_list}"] END'
            elif self.type == Conversation.Filter.Type.KIND:
                return f"kind={str(self.val)} "
            elif self.type == Conversation.Filter.Type.WEEK:
                return f"week={str(self.val)} "
            else:
                return ""

    kind: int
    title: str | None = field(default=None)
