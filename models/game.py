from dataclasses import dataclass
from models.player import Player
from models.card import Deck, Card
from models.chip import ChipHolder

@dataclass
class PokerState:
    blind_amount: int
    players: list[Player]
    community_cards: list[Card]
    burn_cards: list[Card]
    pot: ChipHolder
    dealer_index: int
    current_player: int
    deck: Deck
    phase: str
