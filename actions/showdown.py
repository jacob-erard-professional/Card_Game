import logging
from collections import Counter
from itertools import combinations

from models.card import Card
from models.game import PokerState
from models.player import Player

logger = logging.getLogger(__name__)


def award_pot(game: PokerState) -> list[Player]:
    """Pay out the pot, including side pots, and return the winners best hand first."""
    shares, ranks = pot_shares(game.players, game.community_cards, game.pot)
    by_seat = {p.seat: p for p in game.players}
    for seat, amount in shares.items():
        player = by_seat[seat]
        player.chips += amount
        game.pot -= amount
        if ranks:
            logger.info("Player %s wins $%s with %s", seat, amount, hand_name(ranks[seat]))
        else:
            logger.info("Player %s wins $%s (everyone else folded)", seat, amount)

    winners = [by_seat[seat] for seat in shares]
    if ranks:
        winners.sort(key=lambda p: ranks[p.seat], reverse=True)
    return winners


def pot_shares(players: list[Player], board: list[Card], pot: int) -> tuple[dict[int, int], dict[int, tuple]]:
    """Work out who wins how much of `pot` without changing any state.

    Each player's `committed` total defines the side-pot layers: a layer is
    contested only by the live players who put at least that much in. Returns
    ({seat: chips won}, {seat: hand rank}); ranks are empty when nobody showed down.
    """
    contenders = [p for p in players if p.in_hand]
    if not contenders:
        raise ValueError("No active players to award the pot to")
    if len(contenders) == 1:
        return {contenders[0].seat: pot}, {}

    ranks = {p.seat: evaluate_hand(p.hand + board) for p in contenders}
    shares: dict[int, int] = {}
    remaining = pot
    previous = 0
    carry = 0

    for level in sorted({p.committed for p in players if p.committed > 0}):
        contributors = [p for p in players if p.committed >= level]
        layer = (level - previous) * len(contributors) + carry
        previous = level
        eligible = [p for p in contributors if p.in_hand]
        if not eligible:
            carry = layer
            continue
        carry = 0
        layer = min(layer, remaining)
        remaining -= layer
        _split(shares, eligible, ranks, layer)

    if remaining > 0:
        # Folded money above every live player's commitment goes to the best live hand.
        _split(shares, contenders, ranks, remaining)
    return shares, ranks


def _split(shares: dict[int, int], eligible: list[Player], ranks: dict[int, tuple], amount: int) -> None:
    best = max(ranks[p.seat] for p in eligible)
    winners = [p for p in eligible if ranks[p.seat] == best]
    share, remainder = divmod(amount, len(winners))
    for i, player in enumerate(winners):
        shares[player.seat] = shares.get(player.seat, 0) + share + (1 if i < remainder else 0)


def evaluate_hand(cards: list[Card]) -> tuple:
    """Rank the best 5-card hand within `cards` (5 to 7 cards). Higher tuples are better.

    Returns: (hand_type, *tiebreakers)
    Hand types: 9=Straight Flush, 8=Four of a Kind, 7=Full House,
                6=Flush, 5=Straight, 4=Three of a Kind, 3=Two Pair,
                2=One Pair, 1=High Card
    """
    if len(cards) < 5:
        raise ValueError("Need at least 5 cards to evaluate")

    rank_counts = Counter(card.rank.value for card in cards)
    by_suit: dict = {}
    for card in cards:
        by_suit.setdefault(card.suit, []).append(card.rank.value)
    flush = next((sorted(ranks, reverse=True) for ranks in by_suit.values() if len(ranks) >= 5), None)

    if flush:
        straight_flush = straight_high(flush)
        if straight_flush:
            return (9, straight_flush)

    distinct = sorted(rank_counts, reverse=True)
    quads = [r for r in distinct if rank_counts[r] == 4]
    trips = [r for r in distinct if rank_counts[r] == 3]
    pairs = [r for r in distinct if rank_counts[r] == 2]

    if quads:
        return (8, quads[0], max(r for r in distinct if r != quads[0]))
    if trips and (len(trips) > 1 or pairs):
        return (7, trips[0], max(trips[1:] + pairs))
    if flush:
        return (6, *flush[:5])
    straight = straight_high(distinct)
    if straight:
        return (5, straight)
    if trips:
        return (4, trips[0], *[r for r in distinct if r != trips[0]][:2])
    if len(pairs) >= 2:
        return (3, pairs[0], pairs[1], max(r for r in distinct if r not in pairs[:2]))
    if pairs:
        return (2, pairs[0], *[r for r in distinct if r != pairs[0]][:3])
    return (1, *distinct[:5])


def best_five(cards: list[Card]) -> list[Card]:
    """The five cards that make the best hand within `cards`, grouped the way you'd read them:
    sets first (bigger, then higher), so two pair comes out 9 9 6 6 K rather than 6 9 6 9 K."""
    five = max(combinations(cards, 5), key=lambda five: evaluate_hand(list(five)))
    counts = Counter(card.rank.value for card in five)
    rank = evaluate_hand(list(five))
    if rank[0] in (5, 9) and rank[1] == 5:
        # The wheel plays its ace low.
        return sorted(five, key=lambda card: card.rank.value % 14, reverse=True)
    return sorted(five, key=lambda card: (counts[card.rank.value], card.rank.value), reverse=True)


def straight_high(ranks) -> int | None:
    """Return the high card of the best straight in `ranks`, or None. The wheel (A-2-3-4-5) is 5-high."""
    mask = 0
    for rank in ranks:
        mask |= 1 << rank
    if mask & (1 << 14):
        mask |= 1 << 1
    for high in range(14, 4, -1):
        window = 0b11111 << (high - 4)
        if mask & window == window:
            return high
    return None


HAND_NAMES = {
    9: "Straight Flush",
    8: "Four of a Kind",
    7: "Full House",
    6: "Flush",
    5: "Straight",
    4: "Three of a Kind",
    3: "Two Pair",
    2: "One Pair",
    1: "High Card",
}


def hand_name(hand_rank: tuple) -> str:
    return HAND_NAMES.get(hand_rank[0], "Unknown")


RANK_NAMES = {
    2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight",
    9: "Nine", 10: "Ten", 11: "Jack", 12: "Queen", 13: "King", 14: "Ace",
}
# How many leading tiebreakers are part of the hand itself (the rest are kickers).
MADE_RANKS = {9: 1, 8: 1, 7: 2, 6: 1, 5: 1, 4: 1, 3: 2, 2: 1, 1: 1}


def _plural(rank: int) -> str:
    return "Sixes" if rank == 6 else f"{RANK_NAMES[rank]}s"


def describe_hand(hand_rank: tuple) -> str:
    """Name a hand with its ranks, e.g. 'Three of a Kind, Sevens' or 'Full House, Kings full of Fives'."""
    kind, *ranks = hand_rank
    if kind == 9:
        return "Royal Flush" if ranks[0] == 14 else f"Straight Flush, {RANK_NAMES[ranks[0]]} high"
    if kind == 8:
        return f"Four of a Kind, {_plural(ranks[0])}"
    if kind == 7:
        return f"Full House, {_plural(ranks[0])} full of {_plural(ranks[1])}"
    if kind in (6, 5, 1):
        return f"{HAND_NAMES[kind]}, {RANK_NAMES[ranks[0]]} high"
    if kind == 4:
        return f"Three of a Kind, {_plural(ranks[0])}"
    if kind == 3:
        return f"Two Pair, {_plural(ranks[0])} and {_plural(ranks[1])}"
    return f"One Pair, {_plural(ranks[0])}"


def kicker_decided(winner: tuple, loser: tuple) -> str | None:
    """When two hands of the same kind are separated only by a kicker, name it ('Ace kicker'); otherwise None."""
    if winner[0] != loser[0] or winner == loser:
        return None
    first_difference = next(i for i, (a, b) in enumerate(zip(winner, loser)) if a != b)
    if first_difference <= MADE_RANKS[winner[0]]:
        return None
    return f"{RANK_NAMES[winner[first_difference]]} kicker"
