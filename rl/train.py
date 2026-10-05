"""Train one NFSP bot per table size by self-play in sit-and-go tournaments.

    python -m rl.train --players 2 3 4 5 --hands 300000
    python -m rl.train --players 5 --hands 400000 --resume   # carries on up to 400k total

Every seat at the table is played by the same agent (shared weights), so each
hand produces training data from every seat.
"""
from __future__ import annotations

import argparse
import random
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import torch

from providers import call_provider, random_choice_provider
from rl.actions import action_from_index, legal_action_mask
from rl.encoding import observation_size, observation_vector
from rl.nfsp import AVERAGE, BEST_RESPONSE, NFSPAgent, NFSPConfig, resolve_device
from rl.policy import CHECKPOINT_DIR, PolicyBot, checkpoint_path
from rl.tournament import Tournament, TournamentConfig


def play_training_hand(tournament: Tournament, agent: NFSPAgent, epsilon: float) -> int:
    """Play one self-play hand, feeding both buffers. Returns the number of decisions made."""
    if tournament.finished:
        tournament.reset()
    tournament.start_hand()
    engine = tournament.engine
    payouts = tournament.config.payouts
    modes = {
        p.seat: BEST_RESPONSE if agent.rng.random() < agent.config.eta else AVERAGE
        for p in engine.game.players
    }
    pending: dict[int, tuple[np.ndarray, int]] = {}
    decisions = 0

    while not engine.hand_over:
        seat = engine.current_actor
        obs = observation_vector(engine, seat, payouts)
        mask = legal_action_mask(engine)
        if seat in pending:
            prev_obs, prev_action = pending[seat]
            agent.record_rl(prev_obs, prev_action, 0.0, obs, mask, False)

        action = agent.act(obs, mask, modes[seat], epsilon)
        if modes[seat] == BEST_RESPONSE:
            agent.record_sl(obs, action, mask)
        pending[seat] = (obs, action)
        engine.step(action_from_index(engine, action))
        decisions += 1

    rewards = tournament.finish_hand()
    for seat, (obs, action) in pending.items():
        agent.record_rl(obs, action, rewards[seat], None, None, True)
    return decisions


def evaluate(bot: PolicyBot, num_players: int, opponent, tournaments: int, seed: int) -> float:
    """Average prize share the bot wins in seat 0 against `opponent` in every other seat."""
    rng = random.Random(seed)
    total = 0.0
    for _ in range(tournaments):
        tournament = Tournament(TournamentConfig(num_players=num_players), rng)
        engine = tournament.engine
        engine.set_global_action_provider(opponent)
        engine.set_action_provider(0, bot)
        while not tournament.finished:
            tournament.start_hand()
            while not engine.hand_over:
                player = engine.game.players[engine.current_actor]
                engine.step(engine.action_providers[player.seat](engine, player))
            tournament.finish_hand()
        total += tournament.results()[0]
    return total / tournaments


def save(agent: NFSPAgent, num_players: int, payouts: list[float], hands: int) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "num_players": num_players,
        "obs_size": agent.obs_size,
        "hidden": agent.config.hidden,
        "payouts": payouts,
        "hands_trained": hands,
    }
    policy = {k: v.detach().cpu() for k, v in agent.pi.state_dict().items()}
    torch.save({"meta": meta, "policy": policy}, checkpoint_path(num_players))
    torch.save({**agent.training_state(), "meta": meta}, training_path(num_players))


def training_path(num_players: int) -> Path:
    return CHECKPOINT_DIR / f"rl_{num_players}p.train.pt"


def train(
    num_players: int,
    hands: int,
    config: NFSPConfig,
    device: torch.device,
    eval_every: int,
    eval_tournaments: int,
    resume: bool,
    seed: int,
) -> NFSPAgent:
    """Train up to `hands` in total; a resumed run picks up where the checkpoint left off,
    so the exploration schedule is the same as if training had never stopped."""
    agent = NFSPAgent(observation_size(num_players), config, device, seed)
    hands_done = 0
    if resume and training_path(num_players).exists():
        state = torch.load(training_path(num_players), map_location=device)
        agent.load_training_state(state)
        hands_done = state["meta"]["hands_trained"]
        print(f"[{num_players}p] resumed from {hands_done} hands")

    # Offset the seeds by progress so a resumed run doesn't replay the same deals.
    random.seed(seed + hands_done)
    torch.manual_seed(seed + hands_done)
    tournament = Tournament(TournamentConfig(num_players=num_players), random.Random(seed + hands_done))
    payouts = tournament.config.payouts
    target = hands
    print(f"[{num_players}p] training {max(0, target - hands_done)} hands (to {target}) on {device} | {asdict(config)}")
    started = time.time()
    window_start, window_decisions = time.time(), 0

    while hands_done < target:
        progress = hands_done / target
        epsilon = config.epsilon_start + (config.epsilon_end - config.epsilon_start) * min(1.0, progress / 0.6)
        window_decisions += play_training_hand(tournament, agent, epsilon)
        hands_done += 1

        if hands_done % eval_every == 0 or hands_done == target:
            save(agent, num_players, payouts, hands_done)
            bot = PolicyBot.load(checkpoint_path(num_players), seed=seed)
            fair = 1.0 / num_players
            vs_random = evaluate(bot, num_players, random_choice_provider, eval_tournaments, seed)
            vs_caller = evaluate(bot, num_players, call_provider, eval_tournaments, seed + 1)
            elapsed = time.time() - window_start
            stats = getattr(agent, "last_stats", {})
            print(
                f"[{num_players}p] hands={hands_done:>8} "
                f"decisions/s={window_decisions / elapsed:7.0f} eps={epsilon:.3f} "
                f"q_loss={stats.get('q_loss', float('nan')):.4f} pi_loss={stats.get('pi_loss', float('nan')):.4f} "
                f"prize share vs random={vs_random:.3f} vs caller={vs_caller:.3f} (fair={fair:.3f}) "
                f"elapsed={(time.time() - started) / 60:.1f}m",
                flush=True,
            )
            window_start, window_decisions = time.time(), 0
    return agent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--players", type=int, nargs="+", default=[2, 3, 4, 5], choices=[2, 3, 4, 5])
    parser.add_argument("--hands", type=int, default=300_000, help="total hands to train each table size to (a resumed run trains the remainder)")
    parser.add_argument("--device", default="auto", help="auto, cpu, mps or cuda; auto prefers mps then cuda")
    parser.add_argument("--hidden", type=int, default=NFSPConfig.hidden)
    parser.add_argument("--batch-size", type=int, default=NFSPConfig.batch_size)
    parser.add_argument("--eval-every", type=int, default=10_000)
    parser.add_argument("--eval-tournaments", type=int, default=100)
    parser.add_argument("--resume", action="store_true", help="continue from rl/checkpoints/rl_<n>p.train.pt")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--threads", type=int, default=2, help="CPU threads for acting; keep low when running several trainers")
    args = parser.parse_args()
    torch.set_num_threads(args.threads)

    device = resolve_device(args.device)
    config = NFSPConfig(hidden=args.hidden, batch_size=args.batch_size)
    for num_players in args.players:
        train(num_players, args.hands, config, device, args.eval_every, args.eval_tournaments, args.resume, args.seed)


if __name__ == "__main__":
    main()
