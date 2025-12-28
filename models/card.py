from dataclasses import dataclass
from enum import Enum
import random

class Suit(Enum):
    HEARTS = "H"
    DIAMONDS = "D"
    CLUBS = "C"
    SPADES = "S"

class Rank(Enum):
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14

@dataclass(frozen=True)
class Card:
    rank: Rank
    suit: Suit


class Deck:
    def __init__(self):
        self.cards = [
            Card(rank, suit)
            for suit in Suit
            for rank in Rank
        ]
        random.shuffle(self.cards)

    def draw(self) -> Card:
        return self.cards.pop()