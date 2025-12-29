from engine import PokerEngine
from AP_and_RL.action_providers import call_AP, fold_AP, allin_AP

# Simple initialization with defaults
game = PokerEngine(num_players=2)

game.set_action_providers({1:call_AP, 0:allin_AP})

# Run a hand
game.deal()
print(game.game.community_cards)
game.preflop_betting_round()
game.flop()
print(game.game.community_cards)
game.postflop_betting_round()
game.turn()
print(game.game.community_cards)
game.postflop_betting_round()  
game.river()
print(game.game.community_cards)
print('meow', game.game.players[0].hand, game.game.players[1].hand)
game.postflop_betting_round() 
print(game.showdown())
