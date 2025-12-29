from models.player import Player
from models.game import PokerState

def call_AP(game: PokerState, player: Player) -> str:
    return 'call'

def fold_AP(game:PokerState, player:Player)-> str:
    return 'fold'

def allin_AP(game:PokerState, player:Player)-> str:
    return 'allin'