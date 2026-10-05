"""Action providers: functions that pick a move for a player given the engine."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from actions.action import Action, ActionType
from models.player import Player

if TYPE_CHECKING:
    from engine import PokerEngine


def call_provider(engine: PokerEngine, player: Player) -> str:
    return "call"


def fold_provider(engine: PokerEngine, player: Player) -> str:
    return "fold"


def allin_provider(engine: PokerEngine, player: Player) -> str:
    return "allin"


RANDOM_WEIGHTS = {
    ActionType.CHECK: 5,
    ActionType.CALL: 5,
    ActionType.RAISE: 3,
    ActionType.ALL_IN: 1,
    ActionType.FOLD: 1,
}


def random_choice_provider(engine: PokerEngine, player: Player) -> Action:
    """Pick a legal action at random, favouring passive play. Raises go to a random legal total."""
    legal = engine.legal_actions(player.seat)
    action = random.choices(legal, weights=[RANDOM_WEIGHTS[a.action_type] for a in legal])[0]
    if action.action_type == ActionType.RAISE:
        min_total, max_total = engine.raise_bounds(player.seat)
        return Action.raise_to(random.randint(min_total, min(max_total, min_total * 3)))
    return action


def console_provider(engine: PokerEngine, player: Player) -> str:
    game = engine.game
    print(f"\nPot: {game.pot} | Board: {game.community_cards} | Bet to match: {engine.current_bet}")
    prompt = (f"Player {player.seat} {player.hand} "
              f"(chips={player.chips}, bet={player.bet}) "
              f"action [fold/check/call/raise <total>/allin]: ")
    return input(prompt).strip()
