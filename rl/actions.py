from __future__ import annotations

import numpy as np

from actions.action import Action, ActionType

# Discrete actions: fold, check/call, raise half pot, raise pot, raise 2x pot, all-in.
ACTION_COUNT = 6
RAISE_FRACTIONS = {2: 0.5, 3: 1.0, 4: 2.0}


def legal_action_mask(engine) -> np.ndarray:
    """Which discrete actions are legal for the current actor. Folding is masked when checking is free."""
    legal_types = {action.action_type for action in engine.legal_actions()}
    can_raise = ActionType.RAISE in legal_types
    return np.array([
        ActionType.FOLD in legal_types and ActionType.CALL in legal_types,
        ActionType.CHECK in legal_types or ActionType.CALL in legal_types,
        can_raise,
        can_raise,
        can_raise,
        ActionType.ALL_IN in legal_types,
    ], dtype=bool)


def action_from_index(engine, action_index: int) -> Action:
    """Map a discrete action to a legal engine action. Pot-sized raises are the call plus the pot after calling."""
    if action_index == 0:
        return Action.fold()
    if action_index == 1:
        return Action.call()
    if action_index == 5:
        return Action.all_in()

    player = engine.game.players[engine.current_actor]
    to_call = engine.current_bet - player.bet
    target = engine.current_bet + int((engine.game.pot + to_call) * RAISE_FRACTIONS[action_index])
    min_total, max_total = engine.raise_bounds()
    return Action.raise_to(min(max_total, max(min_total, target)))
