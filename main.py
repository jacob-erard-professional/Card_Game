from engine import PokerEngine
from AP.action_providers import call_AP, fold_AP, allin_AP

# Simple initialization with defaults
game = PokerEngine(num_players=2)

game.set_action_providers({1:call_AP})

# Run a hand
game.deal()
for i, player in enumerate(game.game.players):
    print(i, player.hand)
game.preflop_betting_round()
game.flop()
print(game.game.community_cards)
game.postflop_betting_round()
game.turn()
print(game.game.community_cards)
game.postflop_betting_round()  
game.river()
print(game.game.community_cards)
game.postflop_betting_round() 
print(game.showdown())
