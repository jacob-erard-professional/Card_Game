from models.card import Suit, Rank, Card, Deck
from models.chip import ChipHolder, Chip
from models.game import PokerState
from models.player import Player
from typing import Callable, Dict, Optional
import actions.dealing as dealing
from actions.betting import BettingManager
from actions.showdown import ShowdownManager


class PokerEngine:
    """
    Manages poker game flow including betting rounds, blinds, and player actions.
    """
    
    def __init__(self, num_players: int = 3, blind_amount: int = 20, chip_breakdown: Optional[dict] = None, denominations: Optional[list] = None):
        """
        Initialize a new poker game.
        
        Args:
            num_players: Number of players (default: 3)
            blind_amount: Small blind amount (default: 20)
            chip_breakdown: Dict mapping chip values to quantities (default: {5: 100, 25: 40, 100: 20})
            denominations: List of chip denominations (default: [5, 25, 100])
        """
        if chip_breakdown is None:
            chip_breakdown = {5: 100, 25: 40, 100: 20}
        if denominations is None:
            denominations = [5, 25, 100]
        
        self.chip_breakdown = chip_breakdown
        self.game = self._initialize_game(num_players, blind_amount, chip_breakdown, denominations)
        self.action_providers: Optional[Dict[int, Callable[[PokerState, Player], str]]] = None
        self.betting_manager = BettingManager(self.game, self.action_providers)
        self.showdown_manager = ShowdownManager(self.game, self.action_providers)
        self.players_to_add = []
    
    def set_action_providers(self, providers: Dict[int, Callable[[PokerState, Player], str]]):
        """Set custom action providers for networked/AI play."""
        self.action_providers = providers
        self.betting_manager.action_providers = providers
        self.showdown_manager.action_providers = providers
    
    def preflop_betting_round(self):
        """Execute the preflop betting round with blinds."""
        self.betting_manager.preflop_betting_round()
    
    def postflop_betting_round(self):
        """Execute a postflop betting round (flop, turn, or river)."""
        self.betting_manager.postflop_betting_round()

    def showdown(self) -> list:
        """
        Resolve the showdown: determine winner(s) and award pot.
        Returns list of winner Player objects.
        """
        return self.showdown_manager.execute_showdown()

    def next_round(self):
        """
        Prepare for the next round:
        1. Clear all player hands
        2. Reset folded status for all players
        3. Remove players with no chips
        4. Move dealer index to next player
        5. Clear community cards and burn cards
        """
        # Use PokerState helpers to reset round state
        self.game.reset_round_state()

        # Eventually add players here for networked play

        # Remove players with no chips and reindex
        self.game.remove_broke_players()

        # Advance dealer to next player
        self.game.advance_dealer()

    # No checks on the state of the game, perhaps something that needs to be done but probably not
    def flop(self):
        dealing.flop(self.game)
        
    def turn(self):
        dealing.turn(self.game)
    
    def river(self):
        dealing.river(self.game)
        
    def deal(self):
        dealing.deal(self.game)
    
    def add_player(self, name):
        """
        This is going to eventually be used for network play. The get_id function hasn't been implemented,
        there needs to be a lock to prevent race conditions, and I didn't check if the chip_breakdown works
        yet.
        """
        return
        
        
            
        
    # ========== Private/Internal Methods ==========
    
    def _initialize_game(self, num_players: int, blind_amount: int, 
                        chip_breakdown: dict, denominations: list) -> PokerState:
        """Create and initialize the game state."""
        players = []
        for i in range(num_players):
            player = Player(player_num=i, chips=ChipHolder(chip_breakdown))
            players.append(player)
        
        game = PokerState(
            blind_amount=blind_amount,
            players=players,
            community_cards=[],
            burn_cards=[],
            pot=ChipHolder(),
            dealer_index=0,
            current_player=1,
            deck=Deck(),
            phase="preflop"
        )
        
        return game

# Standalone function for custom initialization if needed
def initialize_game(num_players: int, blind_amount: int, 
                   chip_breakdown: dict, denominations: list) -> PokerState:
    """
    Lightweight wrapper that returns a `PokerState` using `PokerEngine`.
    Keeps the old function API but avoids duplicating initialization logic.
    """
    pe = PokerEngine(num_players=num_players, blind_amount=blind_amount,
                     chip_breakdown=chip_breakdown, denominations=denominations)
    return pe.game