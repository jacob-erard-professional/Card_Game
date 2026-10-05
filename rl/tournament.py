"""Sit-and-go tournament driver and ICM prize equity, used as the RL reward."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from actions.showdown import pot_shares
from engine import PokerEngine
from models.card import Card, Rank, Suit

PAYOUTS = {
    2: [1.0],
    3: [0.7, 0.3],
    4: [0.65, 0.35],
    5: [0.5, 0.3, 0.2],
}
# Small blinds per level; the big blind is double.
BLIND_LEVELS = [10, 15, 25, 40, 60, 80, 100, 150, 200, 300, 400, 500, 600, 800, 1000, 1500, 2000, 3000, 4000, 5000]
# Rewards are reported in percent of the prize pool.
REWARD_SCALE = 100.0
FULL_DECK = [Card(rank, suit) for suit in Suit for rank in Rank]


def icm_equities(stacks: dict[int, int], payouts: list[float]) -> dict[int, float]:
    """Malmuth-Harville ICM: each player's expected share of the prize pool.

    The chance of finishing next is proportional to stack size among the players remaining.
    """
    equities = {seat: 0.0 for seat in stacks}
    alive = tuple(seat for seat, chips in stacks.items() if chips > 0)

    def place_from(remaining: tuple, place: int, prob: float) -> None:
        total = sum(stacks[s] for s in remaining)
        for seat in remaining:
            p = prob * stacks[seat] / total
            equities[seat] += p * payouts[place]
            if place + 1 < len(payouts) and len(remaining) > 1:
                place_from(tuple(s for s in remaining if s != seat), place + 1, p)

    if alive:
        place_from(alive, 0, 1.0)
    return equities


@dataclass
class TournamentConfig:
    num_players: int
    payouts: list[float] = field(default_factory=list)
    hands_per_level: int = 10
    stack_bb_choices: tuple[int, ...] = (50, 75, 100, 125, 150)
    max_hands: int = 400
    runout_samples: int = 48

    def __post_init__(self):
        if not self.payouts:
            self.payouts = PAYOUTS[self.num_players]


class Tournament:
    """Runs one freezeout at a time and scores each hand by the change in ICM equity.

    When a hand is decided by an all-in runout, the "after" equity is averaged over
    possible runouts instead of the one dealt, which removes the luck of the board.
    """

    def __init__(self, config: TournamentConfig, rng: random.Random | None = None):
        self.config = config
        self.rng = rng or random.Random()
        self.reset()

    def reset(self) -> None:
        bb = BLIND_LEVELS[0] * 2
        stack = bb * self.rng.choice(self.config.stack_bb_choices)
        self.engine = PokerEngine(num_players=self.config.num_players, blind_amount=BLIND_LEVELS[0], starting_stack=stack)
        self.engine.game.dealer_index = self.rng.randrange(self.config.num_players)
        self.locked_payouts: dict[int, float] = {}
        self.hands_played = 0

    @property
    def finished(self) -> bool:
        return len(self.engine.game.players_with_chips()) < 2 or self.hands_played >= self.config.max_hands

    def start_hand(self) -> None:
        level = min(self.hands_played // self.config.hands_per_level, len(BLIND_LEVELS) - 1)
        self.engine.game.blind_amount = BLIND_LEVELS[level]
        stacks = {p.seat: p.chips for p in self.engine.game.players}
        self._equity_before = self.equities(stacks, stacks)
        self.engine.start_hand()

    def finish_hand(self) -> dict[int, float]:
        """Score the finished hand for every seat, then move to the next hand."""
        engine = self.engine
        stacks = {p.seat: p.chips for p in engine.game.players}
        after = self._expected_equity_after()
        rewards = {seat: (after[seat] - self._equity_before[seat]) * REWARD_SCALE for seat in stacks}
        self.locked_payouts.update(self._bust_payouts(stacks, engine.starting_stacks))
        engine.next_round()
        self.hands_played += 1
        return rewards

    def results(self) -> dict[int, float]:
        """Prize share per seat: locked payouts for busted players, ICM for anyone still alive."""
        stacks = {p.seat: p.chips for p in self.engine.game.players}
        return self.equities(stacks, stacks)

    def equities(self, stacks: dict[int, int], start_stacks: dict[int, int]) -> dict[int, float]:
        equities = dict(self.locked_payouts)
        equities.update(self._bust_payouts(stacks, start_stacks))
        alive = {seat: chips for seat, chips in stacks.items() if chips > 0}
        equities.update(icm_equities(alive, self.config.payouts))
        return {seat: equities.get(seat, 0.0) for seat in stacks}

    def _bust_payouts(self, stacks: dict[int, int], start_stacks: dict[int, int]) -> dict[int, float]:
        """Payouts for players who just busted. Whoever started the hand bigger places higher."""
        payouts = self.config.payouts
        newly_busted = [s for s, chips in stacks.items() if chips == 0 and s not in self.locked_payouts]
        newly_busted.sort(key=lambda s: start_stacks[s], reverse=True)
        place = sum(1 for chips in stacks.values() if chips > 0)
        result = {}
        i = 0
        while i < len(newly_busted):
            tied = [s for s in newly_busted[i:] if start_stacks[s] == start_stacks[newly_busted[i]]]
            places = range(place + i, place + i + len(tied))
            share = sum(payouts[p] if p < len(payouts) else 0.0 for p in places) / len(tied)
            for seat in tied:
                result[seat] = share
            i += len(tied)
        return result

    def _expected_equity_after(self) -> dict[int, float]:
        engine = self.engine
        players = engine.game.players
        start = engine.starting_stacks
        if engine.runout_from is None:
            return self.equities({p.seat: p.chips for p in players}, start)

        known = engine.game.community_cards[:engine.runout_from]
        live_cards = {card for p in players if p.in_hand for card in p.hand}
        unknown = [c for c in FULL_DECK if c not in live_cards and c not in known]
        missing = 5 - len(known)
        if missing == 1:
            runouts = [[card] for card in unknown]
        else:
            runouts = [self.rng.sample(unknown, missing) for _ in range(self.config.runout_samples)]

        pot = sum(p.committed for p in players)
        base = {p.seat: start[p.seat] - p.committed for p in players}
        totals = {p.seat: 0.0 for p in players}
        for extra in runouts:
            shares, _ = pot_shares(players, known + extra, pot)
            stacks = {seat: chips + shares.get(seat, 0) for seat, chips in base.items()}
            for seat, equity in self.equities(stacks, start).items():
                totals[seat] += equity
        return {seat: total / len(runouts) for seat, total in totals.items()}
