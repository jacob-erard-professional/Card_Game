from models.card import Suit, Rank, Card, Deck
from models.chip import ChipHolder, Chip
from models.game import PokerState
from models.player import Player
import actions.dealing as dealing
from actions.showdown import showdown, award_pot


def initialize_game(num_players, blind_amount, chip_breakdown: ChipHolder) -> PokerState:
    """Initialize a new poker game with players and chips."""
    
    # Create players
    players = []
    for i in range(num_players):
        player = Player(player_num=i, chips=chip_breakdown.copy())
        players.append(player)
    
    # Create the game state
    game = PokerState(
        blind_amount=blind_amount,
        players=players,
        community_cards=[],
        burn_cards = [],
        pot=ChipHolder(),
        dealer_index=0,
        current_player=1,
        deck=Deck(),
        phase="preflop"
    )
    
    return game

def initial_betting_round(game: PokerState):
    
    
