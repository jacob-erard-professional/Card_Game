from __future__ import annotations

from actions.action import Action, ActionType


ACTION_COUNT = 5


def action_from_index(engine, action_index: int) -> Action:
    """Map a discrete DQN action to a legal poker action."""
    legal = engine.legal_actions()
    legal_types = {action.action_type for action in legal}
    player = engine.game.players[engine.current_actor]

    if action_index == 0 and ActionType.FOLD in legal_types:
        return Action.fold()

    if action_index == 1:
        if ActionType.CHECK in legal_types:
            return Action.check()
        if ActionType.CALL in legal_types:
            return Action.call()

    if action_index in (2, 3) and ActionType.RAISE in legal_types:
        pot = engine.game.pot.total()
        raise_by = max(engine.min_raise, pot // (2 if action_index == 2 else 1))
        min_total = engine.current_bet + engine.min_raise
        max_total = player.bet + player.chips.total()
        total = min(max_total, max(min_total, engine.current_bet + raise_by))
        return Action.raise_to(total)

    if action_index == 4 and ActionType.ALL_IN in legal_types:
        return Action.all_in()

    if ActionType.CHECK in legal_types:
        return Action.check()
    if ActionType.CALL in legal_types:
        return Action.call()
    if ActionType.FOLD in legal_types:
        return Action.fold()
    if ActionType.ALL_IN in legal_types:
        return Action.all_in()

    raise RuntimeError("No legal actions available")
