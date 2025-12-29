import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from engine import PokerEngine
from models.card import Card, Rank, Suit


def scenario_single_active():
    pe = PokerEngine(num_players=3, blind_amount=20, chip_breakdown={5: 100})
    game = pe.game

    # Give the pot some chips
    game.pot.add_chips(5, 10)  # $50

    # Fold players 1 and 2
    game.players[1].folded = True
    game.players[2].folded = True

    before = game.players[0].chips.total()
    winners = pe.showdown()
    after = game.players[0].chips.total()

    # Assertions
    assert len(winners) == 1 and winners[0].player_num == 0, f"Expected player 0 to win, got {[p.player_num for p in winners]}"
    assert after - before == 50, f"Expected player0 to gain 50, got {after - before}"
    assert game.pot.total() == 0, f"Expected pot to be empty, got {game.pot.total()}"


def scenario_two_active_showdown():
    pe = PokerEngine(num_players=3, blind_amount=20, chip_breakdown={5: 100})
    game = pe.game

    # Prepare community cards and hole cards so player0 has best hand
    # Community: 2H, 3H, 4H
    game.community_cards = [Card(Rank.TWO, Suit.HEARTS), Card(Rank.THREE, Suit.HEARTS), Card(Rank.FOUR, Suit.HEARTS)]

    # Player0 hole: 5H, 6H -> makes 2-6 hearts straight flush
    game.players[0].hand = [Card(Rank.FIVE, Suit.HEARTS), Card(Rank.SIX, Suit.HEARTS)]

    # Player1 hole: 7C, 8C -> no better hand
    game.players[1].hand = [Card(Rank.SEVEN, Suit.CLUBS), Card(Rank.EIGHT, Suit.CLUBS)]

    # Ensure player2 folded
    game.players[2].folded = True

    # Put $50 in pot
    game.pot.add_chips(5, 10)

    before0 = game.players[0].chips.total()
    before1 = game.players[1].chips.total()

    winners = pe.showdown()

    after0 = game.players[0].chips.total()
    after1 = game.players[1].chips.total()

    # Assertions
    assert len(winners) >= 1 and winners[0].player_num == 0, f"Expected player 0 among winners, got {[p.player_num for p in winners]}"
    assert after0 - before0 == 50, f"Expected player0 to gain 50, got {after0 - before0}"
    assert after1 == before1, f"Expected player1 unchanged, got {after1 - before1}"
    assert game.pot.total() == 0, f"Expected pot to be empty, got {game.pot.total()}"


if __name__ == '__main__':
    scenario_single_active()
    scenario_two_active_showdown()
    print("All showdown tests passed.")
