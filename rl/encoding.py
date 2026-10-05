"""Turns the engine state into the feature vector the networks see, from one seat's point of view."""
from __future__ import annotations

import math

import numpy as np

from actions.showdown import evaluate_hand, straight_high
from models.card import Suit
from rl.tournament import icm_equities

PHASES = ("preflop", "flop", "turn", "river")
SUITS = list(Suit)
BASE_FEATURES = 52 + 52 + 4 + 9 + 5 + 2 + 8 + 4 + 3 + 4
SEAT_FEATURES = 8


def observation_size(num_players: int) -> int:
    return BASE_FEATURES + SEAT_FEATURES * (num_players - 1)


def card_index(card) -> int:
    return SUITS.index(card.suit) * 13 + card.rank.value - 2


def _bb(amount: float, bb: int) -> float:
    """Chip amounts in big blinds, log-scaled so 1bb and 200bb both stay in a sane range."""
    return math.log1p(max(0.0, amount) / bb) / 5.0


def observation_vector(engine, seat: int, payouts: list[float], num_seats: int | None = None) -> np.ndarray:
    """Encode the state for `seat`.

    `num_seats` lets a bot trained for a bigger table play a smaller one: the seats
    that don't exist are encoded as busted players sitting out.
    """
    game = engine.game
    players = game.players
    count = num_seats or len(players)
    if count < len(players):
        raise ValueError(f"A {count}-seat observation cannot describe a {len(players)}-player table")
    me = players[seat]
    bb = max(1, game.blind_amount * 2)
    board = game.community_cards
    obs = np.zeros(observation_size(count), dtype=np.float32)

    # Cards: hole and board as one-hot over the 52-card deck.
    for card in me.hand:
        obs[card_index(card)] = 1.0
    for card in board:
        obs[52 + card_index(card)] = 1.0
    i = 104

    obs[i + PHASES.index(game.phase)] = 1.0
    i += 4

    # Best made hand so far.
    known = me.hand + board
    if len(known) >= 5:
        obs[i + evaluate_hand(known)[0] - 1] = 1.0
    i += 9

    # Starting hand shape.
    if len(me.hand) == 2:
        high, low = sorted((c.rank.value for c in me.hand), reverse=True)
        obs[i:i + 5] = [high == low, me.hand[0].suit == me.hand[1].suit, high / 14, low / 14, (high - low) / 12]
    i += 5

    # Draws, only while more cards are coming.
    if 3 <= len(board) <= 4:
        suit_counts = [sum(1 for c in known if c.suit == suit) for suit in SUITS]
        ranks = {c.rank.value for c in known}
        outs = 0 if straight_high(ranks) else sum(1 for r in range(2, 15) if r not in ranks and straight_high(ranks | {r}))
        obs[i:i + 2] = [max(suit_counts) == 4, min(outs, 2) / 2]
    i += 2

    # Betting.
    to_call = max(0, engine.current_bet - me.bet)
    pot = game.pot
    obs[i:i + 8] = [
        _bb(pot, bb),
        _bb(to_call, bb),
        _bb(engine.min_raise, bb),
        _bb(me.chips, bb),
        _bb(me.bet, bb),
        _bb(me.committed, bb),
        to_call / (pot + to_call) if pot + to_call else 0.0,
        min(me.chips / pot, 10) / 10 if pot else 1.0,
    ]
    i += 8

    # Position, counted clockwise from the seat after the button.
    dealt = [p for p in players if not p.sitting_out]
    order = sorted(dealt, key=lambda p: (p.seat - game.dealer_index - 1) % len(players))
    my_pos = order.index(me)
    acting_after = sum(1 for p in order[my_pos + 1:] if p.in_hand and not p.all_in and p.chips > 0)
    obs[i:i + 4] = [
        my_pos / max(1, len(order) - 1),
        acting_after / count,
        len(dealt) / count,
        sum(1 for p in players if p.in_hand) / count,
    ]
    i += 4

    # Tournament standing, from stacks as they were when the hand began.
    start_stacks = {p.seat: p.chips + p.committed for p in dealt}
    total_chips = sum(start_stacks.values())
    obs[i:i + 3] = [
        start_stacks[seat] / total_chips,
        icm_equities(start_stacks, payouts)[seat],
        min(bb / (total_chips / len(dealt)), 1.0),
    ]
    i += 3

    # Action history.
    actions = [a for a in engine.action_log if a["action"] != "post"]
    street = [a for a in actions if a["phase"] == game.phase]
    aggressors = [a["seat"] for a in actions if a["raised"]]
    obs[i:i + 4] = [
        min(sum(a["raised"] for a in street), 4) / 4,
        min(len(aggressors), 8) / 8,
        bool(aggressors) and aggressors[-1] == seat,
        sum(1 for a in street if a["action"] == "call") / count,
    ]
    i += 4

    # Every other seat, clockwise from me.
    raised_this_street = {a["seat"] for a in street if a["raised"]}
    for offset in range(1, len(players)):
        p = players[(seat + offset) % len(players)]
        obs[i:i + SEAT_FEATURES] = [
            _bb(p.chips, bb),
            _bb(p.bet, bb),
            _bb(p.committed, bb),
            p.in_hand,
            p.all_in,
            p.sitting_out,
            p.seat == game.dealer_index,
            p.seat in raised_this_street,
        ]
        i += SEAT_FEATURES
    for _ in range(count - len(players)):
        obs[i + 5] = 1.0  # sitting out
        i += SEAT_FEATURES

    return obs
