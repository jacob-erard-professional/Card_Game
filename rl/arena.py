"""Pit the bots trained for different table sizes against each other.

    python -m rl.arena --tournaments 2000

A bot can sit at any table no bigger than the one it trained for, so each table
size gets its own leaderboard among the bots that fit. Seats are filled at random
(mirror matches included) and each bot is scored by its average prize share per
seat; 1/table size is break-even.
"""
from __future__ import annotations

import argparse
import math
import random
import time

import torch

from rl.policy import PolicyBot, checkpoint_path
from rl.tournament import Tournament, TournamentConfig


def play_tournament(table_size: int, seating: list[PolicyBot], rng: random.Random) -> dict[int, float]:
    tournament = Tournament(TournamentConfig(num_players=table_size), rng)
    engine = tournament.engine
    while not tournament.finished:
        tournament.start_hand()
        while not engine.hand_over:
            seat = engine.current_actor
            engine.step(seating[seat].act(engine, seat))
        tournament.finish_hand()
    return tournament.results()


def leaderboard(table_size: int, bots: dict[int, PolicyBot], tournaments: int, seed: int) -> list[tuple[int, float, float, int]]:
    """Return (bot size, mean prize share, standard error, seats played), best first."""
    rng = random.Random(seed)
    names = list(bots)
    shares: dict[int, list[float]] = {name: [] for name in names}
    for _ in range(tournaments):
        # Distinct bots when there are enough of them; otherwise every bot plus random repeats.
        if len(names) >= table_size:
            lineup = rng.sample(names, table_size)
        else:
            lineup = names + [rng.choice(names) for _ in range(table_size - len(names))]
        rng.shuffle(lineup)
        for seat, share in play_tournament(table_size, [bots[n] for n in lineup], rng).items():
            shares[lineup[seat]].append(share)

    rows = []
    for name, values in shares.items():
        if not values:
            continue
        mean = sum(values) / len(values)
        var = sum((v - mean) ** 2 for v in values) / max(1, len(values) - 1)
        rows.append((name, mean, math.sqrt(var / len(values)), len(values)))
    return sorted(rows, key=lambda row: row[1], reverse=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tournaments", type=int, default=2000, help="tournaments per table size")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    torch.set_num_threads(1)

    bots = {}
    for size in (2, 3, 4, 5):
        path = checkpoint_path(size)
        if path.exists():
            bot = PolicyBot.load(path, seed=args.seed + size)
            bots[size] = bot
            hands = torch.load(path, map_location="cpu")["meta"].get("hands_trained", "?")
            print(f"loaded {size}p bot ({hands} hands trained)")

    for table_size in (2, 3, 4, 5):
        eligible = {size: bot for size, bot in bots.items() if size >= table_size}
        if len(eligible) < 2:
            continue
        started = time.time()
        print(f"\n{table_size}-handed table, {args.tournaments} tournaments (break-even {1 / table_size:.3f})")
        for name, mean, stderr, seats in leaderboard(table_size, eligible, args.tournaments, args.seed + table_size):
            print(f"  {name}p bot: prize share {mean:.3f} ± {stderr:.3f} over {seats} seats")
        print(f"  ({time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
