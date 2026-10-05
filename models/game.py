from dataclasses import dataclass, field
from typing import List
from models.player import Player
from models.card import Deck, Card


@dataclass
class PokerState:
    blind_amount: int
    players: List[Player]
    dealer_index: int = 0
    pot: int = 0
    community_cards: List[Card] = field(default_factory=list)
    burn_cards: List[Card] = field(default_factory=list)
    deck: Deck = field(default_factory=Deck)
    phase: str = "preflop"

    def reset_round_state(self) -> None:
        """Clear hands, bets, board and pot and shuffle a fresh deck.

        Players without chips sit out the hand but keep their seat.
        """
        for p in self.players:
            p.hand = []
            p.folded = False
            p.sitting_out = p.chips == 0
            p.bet = 0
            p.committed = 0
            p.all_in = False
        self.community_cards = []
        self.burn_cards = []
        self.pot = 0
        self.deck = Deck()

    def players_with_chips(self) -> List[Player]:
        return [p for p in self.players if p.chips > 0]

    def next_seat_with_chips(self, after: int) -> int:
        """Return the index of the first player after `after` (wrapping) who has chips."""
        count = len(self.players)
        for offset in range(1, count + 1):
            idx = (after + offset) % count
            if self.players[idx].chips > 0:
                return idx
        raise ValueError("No player has chips")

    def advance_dealer(self) -> None:
        """Move the button to the next player with chips. Busted seats are skipped, never removed."""
        if self.players_with_chips():
            self.dealer_index = self.next_seat_with_chips(self.dealer_index)
