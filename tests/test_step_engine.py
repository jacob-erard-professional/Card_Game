import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from actions.action import Action, ActionType
from engine import PokerEngine
from rl.environment import PokerRLEnv


def test_legal_actions_and_public_state():
    engine = PokerEngine(num_players=2, blind_amount=20, chip_breakdown={5: 100})
    engine.start_hand()

    current = engine.game.players[engine.current_actor]
    legal = engine.legal_actions(current.player_num)
    legal_types = {action.action_type for action in legal}

    assert ActionType.FOLD in legal_types
    assert ActionType.CALL in legal_types
    assert ActionType.ALL_IN in legal_types
    assert engine.public_state_for(current.player_num)["players"][1 - current.player_num]["hand"] == []


def test_step_hand_conserves_chips_with_random_legal_actions():
    engine = PokerEngine(num_players=4, blind_amount=20, chip_breakdown={5: 100})
    before = sum(p.chips.total() for p in engine.game.players)
    engine.start_hand()

    guard = 0
    while not engine.hand_over:
        guard += 1
        assert guard < 200
        legal = engine.legal_actions()
        passive = [a for a in legal if a.action_type in (ActionType.CHECK, ActionType.CALL)]
        engine.step(passive[0] if passive else legal[0])

    after = sum(p.chips.total() for p in engine.game.players) + engine.game.pot.total()
    assert before == after
    assert engine.last_winners


def test_side_pot_conserves_chips():
    engine = PokerEngine(num_players=3, blind_amount=10, chip_breakdown={1: 100})
    engine.start_hand()

    for player, stack in zip(engine.game.players, [10, 30, 60]):
        player.chips.chips = {1: stack}
        player.bet = 0
        player.committed = 0
        player.folded = False
        player.all_in = False
    engine.game.pot.chips = {}
    engine.current_bet = 0
    engine.min_raise = 10
    engine.has_acted = {p.player_num: False for p in engine.game.players}
    engine.current_actor = 0
    before = sum(p.chips.total() for p in engine.game.players) + engine.game.pot.total()

    while not engine.hand_over:
        engine.step(Action.all_in())

    after = sum(p.chips.total() for p in engine.game.players) + engine.game.pot.total()
    assert before == after


def test_rl_environment_smoke():
    env = PokerRLEnv(num_players=2, blind_amount=20, chip_breakdown={5: 100})
    obs, mask = env.reset()
    assert len(obs) > 0
    assert any(mask)

    result = env.step(next(idx for idx, allowed in enumerate(mask) if allowed))
    assert len(result.observation) == len(obs)


if __name__ == "__main__":
    test_legal_actions_and_public_state()
    test_step_hand_conserves_chips_with_random_legal_actions()
    test_side_pot_conserves_chips()
    test_rl_environment_smoke()
    print("All step engine tests passed.")
