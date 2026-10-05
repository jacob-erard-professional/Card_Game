import random

import numpy as np
import pytest

from actions.action import ActionType
from models.card import Card, Rank, Suit
from rl.actions import ACTION_COUNT, action_from_index, legal_action_mask
from rl.encoding import observation_size, observation_vector
from rl.tournament import PAYOUTS, Tournament, TournamentConfig, icm_equities

torch = pytest.importorskip("torch")


def test_icm_heads_up_winner_take_all_is_chip_share():
    equities = icm_equities({0: 300, 1: 100}, [1.0])
    assert equities == pytest.approx({0: 0.75, 1: 0.25})


def test_icm_equal_stacks_split_evenly_and_sum_to_pool():
    equities = icm_equities({0: 500, 1: 500, 2: 500, 3: 500, 4: 500}, PAYOUTS[5])
    assert sum(equities.values()) == pytest.approx(1.0)
    assert all(e == pytest.approx(0.2) for e in equities.values())


def test_icm_chip_leader_is_worth_less_than_chip_share():
    equities = icm_equities({0: 7000, 1: 1500, 2: 1500}, PAYOUTS[3])
    assert equities[0] < 0.7
    assert sum(equities.values()) == pytest.approx(1.0)


def test_busted_players_lock_in_their_finishing_payout():
    tournament = Tournament(TournamentConfig(num_players=3), random.Random(0))
    tournament.engine.game.players[2].chips = 0
    stacks = {p.seat: p.chips for p in tournament.engine.game.players}
    equities = tournament.equities(stacks, {0: 1000, 1: 1000, 2: 1000})
    assert equities[2] == 0.0  # third place pays nothing in a 3-player 70/30
    assert equities[0] + equities[1] == pytest.approx(1.0)


def test_preflop_all_in_reward_uses_equity_not_the_runout():
    rewards = []
    for seed in range(30):
        tournament = Tournament(TournamentConfig(num_players=2, runout_samples=400), random.Random(seed))
        engine = tournament.engine
        tournament.start_hand()
        aces, kings = engine.game.players[engine.current_actor], engine.game.players[1 - engine.current_actor]
        aces.hand = [Card(Rank.ACE, Suit.SPADES), Card(Rank.ACE, Suit.HEARTS)]
        kings.hand = [Card(Rank.KING, Suit.SPADES), Card(Rank.KING, Suit.HEARTS)]
        engine.step("allin")
        engine.step("call")
        assert engine.runout_from == 0
        rewards.append(tournament.finish_hand()[aces.seat])

    # Equal stacks, all in: aces hold ~82%, so the reward is ~+32% of the pool every time.
    assert all(25 < r < 40 for r in rewards)
    assert np.std(rewards) < 3


def test_hand_rewards_are_zero_sum():
    from rl.train import play_training_hand
    from rl.nfsp import NFSPAgent, NFSPConfig

    agent = NFSPAgent(observation_size(4), NFSPConfig(hidden=32, min_buffer=10**9), torch.device("cpu"), seed=0)
    tournament = Tournament(TournamentConfig(num_players=4), random.Random(0))
    for _ in range(50):
        if tournament.finished:
            tournament.reset()
        tournament.start_hand()
        while not tournament.engine.hand_over:
            engine = tournament.engine
            mask = legal_action_mask(engine)
            obs = observation_vector(engine, engine.current_actor, tournament.config.payouts)
            engine.step(action_from_index(engine, agent.act(obs, mask, "average", 0.0)))
        assert sum(tournament.finish_hand().values()) == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("num_players", [2, 3, 4, 5])
def test_observation_and_mask_shapes(num_players):
    tournament = Tournament(TournamentConfig(num_players=num_players), random.Random(num_players))
    tournament.start_hand()
    engine = tournament.engine
    obs = observation_vector(engine, engine.current_actor, tournament.config.payouts)
    mask = legal_action_mask(engine)
    assert obs.shape == (observation_size(num_players),)
    assert np.isfinite(obs).all()
    assert mask.shape == (ACTION_COUNT,) and mask.any()


def test_every_masked_action_is_legal():
    rng = random.Random(3)
    tournament = Tournament(TournamentConfig(num_players=5), rng)
    for _ in range(300):
        if tournament.finished:
            tournament.reset()
        tournament.start_hand()
        engine = tournament.engine
        while not engine.hand_over:
            legal = np.flatnonzero(legal_action_mask(engine))
            engine.step(action_from_index(engine, int(rng.choice(legal))))  # raises if illegal
        tournament.finish_hand()


def test_fold_is_masked_when_checking_is_free():
    tournament = Tournament(TournamentConfig(num_players=2), random.Random(0))
    tournament.start_hand()
    engine = tournament.engine
    engine.step("call")
    assert {a.action_type for a in engine.legal_actions()} >= {ActionType.CHECK}
    assert not legal_action_mask(engine)[0]


def test_train_save_load_and_play(tmp_path, monkeypatch):
    import rl.policy
    import rl.train
    from rl.nfsp import NFSPConfig
    from rl.policy import PolicyBot

    monkeypatch.setattr(rl.policy, "CHECKPOINT_DIR", tmp_path)
    monkeypatch.setattr(rl.train, "CHECKPOINT_DIR", tmp_path)
    config = NFSPConfig(hidden=32, batch_size=32, min_buffer=64, learn_every=8, rl_capacity=2000, sl_capacity=2000, eta=0.5)
    agent = rl.train.train(3, hands=150, config=config, device=torch.device("cpu"),
                   eval_every=150, eval_tournaments=2, resume=False, seed=1)
    assert agent.learn_steps > 0

    bot = PolicyBot.load(tmp_path / "rl_3p.pt")
    tournament = Tournament(TournamentConfig(num_players=3), random.Random(5))
    tournament.engine.set_global_action_provider(bot)
    tournament.engine.run()


def test_bigger_table_bot_plays_smaller_table(tmp_path, monkeypatch):
    import rl.policy
    import rl.train
    from rl.arena import play_tournament
    from rl.nfsp import NFSPConfig
    from rl.policy import PolicyBot

    monkeypatch.setattr(rl.policy, "CHECKPOINT_DIR", tmp_path)
    monkeypatch.setattr(rl.train, "CHECKPOINT_DIR", tmp_path)
    config = NFSPConfig(hidden=16, batch_size=16, min_buffer=10**9, rl_capacity=100, sl_capacity=100)
    for size in (2, 4):
        rl.train.train(size, hands=1, config=config, device=torch.device("cpu"),
                       eval_every=1, eval_tournaments=1, resume=False, seed=size)

    small, big = PolicyBot.load(tmp_path / "rl_2p.pt"), PolicyBot.load(tmp_path / "rl_4p.pt")
    results = play_tournament(2, [small, big], random.Random(0))
    assert sum(results.values()) == pytest.approx(1.0)


def test_padded_seats_look_like_busted_players():
    tournament = Tournament(TournamentConfig(num_players=2), random.Random(0))
    tournament.start_hand()
    engine = tournament.engine
    obs = observation_vector(engine, engine.current_actor, PAYOUTS[4], num_seats=4)
    assert obs.shape == (observation_size(4),)
    padded = obs[-2 * 8:].reshape(2, 8)
    assert (padded[:, 5] == 1).all() and (padded[:, :5] == 0).all()
