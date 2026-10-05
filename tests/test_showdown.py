from collections import Counter

from actions.showdown import award_pot, best_five, describe_hand, evaluate_hand, kicker_decided
from engine import PokerEngine
from models.card import Card, Rank, Suit


def cards(spec: str) -> list[Card]:
    """Parse e.g. 'AH 2C 10D' into cards."""
    ranks = {"J": Rank.JACK, "Q": Rank.QUEEN, "K": Rank.KING, "A": Rank.ACE}
    out = []
    for token in spec.split():
        rank_text, suit_text = token[:-1], token[-1]
        rank = ranks.get(rank_text) or Rank(int(rank_text))
        out.append(Card(rank, Suit(suit_text)))
    return out


def test_single_active_player_takes_pot():
    game = PokerEngine(num_players=3, starting_stack=500).game
    game.pot = 50
    game.players[1].folded = True
    game.players[2].folded = True

    winners = award_pot(game)

    assert [p.seat for p in winners] == [0]
    assert game.players[0].chips == 550
    assert game.pot == 0


def test_best_hand_takes_pot():
    game = PokerEngine(num_players=3, starting_stack=500).game
    game.community_cards = cards("2H 3H 4H 9S KD")
    game.players[0].hand = cards("5H 6H")
    game.players[1].hand = cards("7C 8C")
    game.players[2].folded = True
    for p in game.players[:2]:
        p.committed = 25
    game.pot = 50

    winners = award_pot(game)

    assert [p.seat for p in winners] == [0]
    assert game.players[0].chips == 550
    assert game.players[1].chips == 500
    assert game.pot == 0


def test_wheel_is_five_high_straight():
    wheel = evaluate_hand(cards("AH 2C 3C 4S 5D"))
    six_high = evaluate_hand(cards("2H 3C 4C 5S 6D"))
    king_high = evaluate_hand(cards("KH QC JC 10S 9D"))
    assert wheel < six_high < king_high


def test_steel_wheel_is_lowest_straight_flush():
    steel_wheel = evaluate_hand(cards("AH 2H 3H 4H 5H"))
    six_high = evaluate_hand(cards("2H 3H 4H 5H 6H"))
    assert steel_wheel < six_high


def test_side_pots_pay_each_layer_to_its_best_eligible_hand():
    game = PokerEngine(num_players=3, starting_stack=0).game
    game.community_cards = cards("2C 7D 9H JS 3C")
    game.players[0].hand = cards("AS AD")  # best hand, covers 10
    game.players[1].hand = cards("KS KD")  # second best, covers 30
    game.players[2].hand = cards("4H 5H")  # worst, covers 60
    for player, committed in zip(game.players, [10, 30, 60]):
        player.committed = committed
    game.pot = 100

    award_pot(game)

    assert [p.chips for p in game.players] == [30, 40, 30]
    assert game.pot == 0


def brute_force_rank(seven: list[Card]) -> tuple:
    """Reference: score every 5-card subset directly."""
    from itertools import combinations

    def five_card_rank(five):
        ranks = sorted((c.rank.value for c in five), reverse=True)
        counts = Counter(ranks)
        shape = sorted(counts.values(), reverse=True)
        grouped = sorted(counts, key=lambda r: (counts[r], r), reverse=True)
        flush = len({c.suit for c in five}) == 1
        unique = sorted(set(ranks))
        straight = None
        if len(unique) == 5 and unique[-1] - unique[0] == 4:
            straight = unique[-1]
        elif unique == [2, 3, 4, 5, 14]:
            straight = 5
        if straight and flush:
            return (9, straight)
        if shape == [4, 1]:
            return (8, *grouped)
        if shape == [3, 2]:
            return (7, *grouped)
        if flush:
            return (6, *ranks)
        if straight:
            return (5, straight)
        if shape == [3, 1, 1]:
            return (4, *grouped)
        if shape == [2, 2, 1]:
            return (3, *grouped)
        if shape == [2, 1, 1, 1]:
            return (2, *grouped)
        return (1, *ranks)

    return max(five_card_rank(five) for five in combinations(seven, 5))


def test_evaluator_matches_brute_force_on_random_hands():
    import random

    from models.card import Deck

    rng = random.Random(1234)
    for _ in range(20000):
        deck = Deck()
        rng.shuffle(deck.cards)
        seven = deck.cards[:rng.choice([5, 6, 7])]
        assert evaluate_hand(seven) == brute_force_rank(seven), seven


def test_best_five_picks_the_cards_that_make_the_hand():
    from actions.showdown import best_five

    seven = cards("AH KH 2C QH JH 7D 10H")
    assert sorted(c.rank.value for c in best_five(seven)) == [10, 11, 12, 13, 14]
    assert evaluate_hand(best_five(seven)) == evaluate_hand(seven)


def test_best_five_reads_in_order():
    two_pair = best_five(cards("7D 6D 9C 6C 9S KC 2H"))
    assert [c.rank.value for c in two_pair] == [9, 9, 6, 6, 13]
    wheel = best_five(cards("AS 2D 3C 4H 5S KD QC"))
    assert [c.rank.value for c in wheel] == [5, 4, 3, 2, 14]


def test_hand_descriptions_name_the_ranks():
    assert describe_hand(evaluate_hand(cards("7D 6D 9C 6C 9S KC 2H"))) == "Two Pair, Nines and Sixes"
    assert describe_hand(evaluate_hand(cards("7S 7H 7D KC QC"))) == "Three of a Kind, Sevens"
    assert describe_hand(evaluate_hand(cards("KS KH KD 5C 5D"))) == "Full House, Kings full of Fives"
    assert describe_hand(evaluate_hand(cards("AH KH QH JH 10H"))) == "Royal Flush"


def test_kicker_named_only_when_it_decides_the_hand():
    board = cards("7S 7H 7D KC 2C")
    ace = evaluate_hand(board + cards("AS 3H"))
    queen = evaluate_hand(board + cards("QD 5H"))
    assert kicker_decided(ace, queen) == "Ace kicker"
    # Higher trips win on the trips themselves, not a kicker.
    assert kicker_decided(evaluate_hand(cards("9S 9H 9D 2C 3D")), evaluate_hand(cards("5S 5H 5D AC KD"))) is None
    # A different kind of hand needs no explanation; neither does a tie.
    assert kicker_decided(evaluate_hand(cards("9S 9H 9D 2C 3D")), evaluate_hand(cards("9C 9H 4D 4C 3D"))) is None
    assert kicker_decided(ace, ace) is None
