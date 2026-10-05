import logging

from engine import PokerEngine
from providers import random_choice_provider

logging.basicConfig(level=logging.INFO, format="%(message)s")

game = PokerEngine(num_players=22)
game.set_global_action_provider(random_choice_provider)
for _ in range(100):
    if len(game.game.players_with_chips()) < 2:
        break
    game.run()
