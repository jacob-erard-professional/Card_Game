from dataclasses import dataclass, field
from typing import List
from models.player import Player
from models.card import Deck, Card
from models.chip import ChipHolder


@dataclass
class PokerState:
    blind_amount: int
    players: List[Player]
    community_cards: List[Card]
    burn_cards: List[Card]
    pot: ChipHolder
    dealer_index: int
    current_player: int
    deck: Deck
    phase: str

    # Convenience / helper methods used by engine and managers
    def active_players(self) -> List[Player]:
        """Return list of players who have not folded."""
        return [p for p in self.players if not p.folded]

    def active_with_chips(self) -> List[Player]:
        """Return list of players who have not folded and have chips remaining."""
        return [p for p in self.players if not p.folded and p.chips.total() > 0]

    def reset_bets(self) -> None:
        """Reset the `bet` field on all players to zero."""
        for p in self.players:
            p.bet = 0

    def reset_round_state(self) -> None:
        """Prepare state for the next round without changing dealer ordering.

        Clears players' hands, folded flags, community/burn cards and resets bets.
        Does not remove players who are out of chips.
        """
        for p in self.players:
            p.hand = []
            p.folded = False
        self.reset_bets()
        self.community_cards = []
        self.burn_cards = []

    def remove_broke_players(self) -> None:
        """Remove players who have no chips left from the game and reindex players.

        Keeps the dealer index within bounds.
        """
        old_dealer = self.dealer_index
        new_players = [p for p in self.players if p.chips.total() > 0]
        # Reassign player_num sequentially
        for i, p in enumerate(new_players):
            p.player_num = i
        self.players = new_players

        if len(self.players) == 0:
            self.dealer_index = 0
        else:
            self.dealer_index = old_dealer % len(self.players)

    def advance_dealer(self) -> None:
        """Move the dealer index to the next player (safely handles removed players)."""
        if len(self.players) == 0:
            self.dealer_index = 0
            return
        self.dealer_index = self.dealer_index % len(self.players)
        self.dealer_index = (self.dealer_index + 1) % len(self.players)

    def pot_total(self) -> int:
        """Return the total chips currently in the pot."""
        return self.pot.total()

