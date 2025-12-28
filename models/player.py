from dataclasses import dataclass, field
from models.chip import ChipHolder
from models.card import Card

@dataclass
class Player:
    player_num: int
    chips: ChipHolder
    name: str = None
    hand: list[Card] = field(default_factory=list)
    folded: bool = False
    bet: int = 0