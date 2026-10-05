from dataclasses import dataclass, field
from models.card import Card

@dataclass
class Player:
    seat: int
    chips: int
    name: str | None = None
    hand: list[Card] = field(default_factory=list)
    folded: bool = False
    bet: int = 0
    committed: int = 0
    all_in: bool = False
    sitting_out: bool = False

    @property
    def in_hand(self) -> bool:
        """Dealt into the current hand and not folded."""
        return not self.sitting_out and not self.folded
