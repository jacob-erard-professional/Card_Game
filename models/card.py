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
    def __repr__(self) -> str:
        """Return a compact human-friendly representation like 'A♥' or '10♦'."""
        suit_symbols = {
            Suit.HEARTS: '♥',
            Suit.DIAMONDS: '♦',
            Suit.CLUBS: '♣',
            Suit.SPADES: '♠',
        }

        rank_names = {
            Rank.ACE: 'A',
            Rank.KING: 'K',
            Rank.QUEEN: 'Q',
            Rank.JACK: 'J',
        }

        rank_str = rank_names.get(self.rank, str(self.rank.value))
        return f"{rank_str}{suit_symbols.get(self.suit, self.suit.value)}"


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