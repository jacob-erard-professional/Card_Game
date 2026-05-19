from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ActionType(str, Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    RAISE = "raise"
    ALL_IN = "allin"


@dataclass(frozen=True)
class Action:
    action_type: ActionType
    amount: Optional[int] = None

    @classmethod
    def fold(cls) -> "Action":
        return cls(ActionType.FOLD)

    @classmethod
    def check(cls) -> "Action":
        return cls(ActionType.CHECK)

    @classmethod
    def call(cls) -> "Action":
        return cls(ActionType.CALL)

    @classmethod
    def raise_to(cls, total_bet: int) -> "Action":
        return cls(ActionType.RAISE, total_bet)

    @classmethod
    def all_in(cls) -> "Action":
        return cls(ActionType.ALL_IN)


def parse_action(value: str | Action) -> Action:
    if isinstance(value, Action):
        return value

    parts = value.strip().lower().split()
    if not parts:
        raise ValueError("Action cannot be empty")

    name = parts[0]
    if name == "fold":
        return Action.fold()
    if name == "check":
        return Action.check()
    if name == "call":
        return Action.call()
    if name == "allin" or name == "all-in":
        return Action.all_in()
    if name == "raise":
        if len(parts) != 2:
            raise ValueError("Raise action must be formatted as 'raise <amount>'")
        try:
            amount = int(parts[1])
        except ValueError as exc:
            raise ValueError("Raise amount must be an integer") from exc
        return Action.raise_to(amount)

    raise ValueError(f"Unknown action: {value}")


def action_to_string(action: Action) -> str:
    if action.action_type == ActionType.RAISE:
        return f"raise {action.amount}"
    return action.action_type.value
