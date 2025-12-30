from engine import PokerEngine
from AP.action_providers import call_AP, fold_AP, allin_AP, random_choice_AP

# Simple initialization with defaults


for _ in range(100):
    game = PokerEngine(num_players=22)
    game.set_global_action_provider(random_choice_AP)
    game.run()
