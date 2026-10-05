import pytest

from actions.action import Action, ActionType
from engine import PokerEngine
from tests.test_showdown import cards


def total_chips(engine: PokerEngine) -> int:
    return sum(p.chips for p in engine.game.players) + engine.game.pot


def test_legal_actions_and_public_state():
    engine = PokerEngine(num_players=2, blind_amount=20, starting_stack=500)
    engine.start_hand()

    current = engine.game.players[engine.current_actor]
    legal_types = {action.action_type for action in engine.legal_actions(current.seat)}

    assert {ActionType.FOLD, ActionType.CALL, ActionType.ALL_IN} <= legal_types
    assert engine.public_state_for(current.seat)["players"][1 - current.seat]["hand"] == []


def test_heads_up_dealer_posts_small_blind_and_acts_first_preflop():
    engine = PokerEngine(num_players=2, blind_amount=20, starting_stack=500)
    engine.start_hand()
    dealer = engine.game.dealer_index
    other = 1 - dealer

    assert engine.game.players[dealer].bet == 20
    assert engine.game.players[other].bet == 40
    assert engine.current_actor == dealer

    engine.step("call")
    engine.step("check")

    assert engine.game.phase == "flop"
    assert engine.current_actor == other


def test_three_handed_blinds_sit_left_of_dealer():
    engine = PokerEngine(num_players=3, blind_amount=20, starting_stack=500)
    engine.start_hand()

    assert [p.bet for p in engine.game.players] == [0, 20, 40]
    assert engine.current_actor == 0


def test_dealer_button_does_not_skip_a_seat_when_a_player_busts():
    engine = PokerEngine(num_players=4, starting_stack=500)
    engine.game.dealer_index = 2
    engine.game.players[1].chips = 0

    engine.next_round()

    assert engine.game.dealer_index == 3


def test_busted_player_keeps_seat_and_sits_out():
    engine = PokerEngine(num_players=3, blind_amount=10, starting_stack=500)
    busted = engine.game.players[1]
    busted.chips = 0
    engine.game.dealer_index = 0

    engine.start_hand()

    assert [p.seat for p in engine.game.players] == [0, 1, 2]
    assert busted.sitting_out and busted.hand == []
    # Two live players left, so heads-up rules: dealer posts the small blind and acts first.
    assert [p.bet for p in engine.game.players] == [10, 0, 20]
    assert engine.current_actor == 0
    assert engine.public_state_for(0)["players"][1]["sitting_out"]


def legal_types(engine):
    return {a.action_type for a in engine.legal_actions()}


def test_short_all_in_does_not_reopen_raising_for_players_who_acted():
    engine = PokerEngine(num_players=3, blind_amount=10, starting_stack=1000)
    engine.game.players[1].chips = 30
    engine.game.dealer_index = 0
    engine.start_hand()  # seat 1 posts SB 10, seat 2 posts BB 20, seat 0 acts first

    engine.step("call")  # seat 0 calls 20
    engine.step("allin")  # seat 1 all-in to 30: a 10 raise, short of the 20 minimum
    assert engine.current_bet == 30

    assert engine.current_actor == 2  # big blind has not acted yet, so may raise
    assert ActionType.RAISE in legal_types(engine)
    engine.step("call")

    assert engine.current_actor == 0
    assert legal_types(engine) == {ActionType.FOLD, ActionType.CALL}
    assert engine.raise_bounds() is None
    with pytest.raises(ValueError):
        engine.step("raise 100")
    engine.step("call")
    assert engine.game.phase == "flop"


def test_short_all_ins_that_add_up_to_a_full_raise_reopen_raising():
    engine = PokerEngine(num_players=4, blind_amount=10, starting_stack=1000)
    engine.game.players[0].chips = 35
    engine.game.players[1].chips = 50
    engine.game.dealer_index = 0
    engine.start_hand()  # SB seat 1, BB seat 2, seat 3 acts first

    engine.step("call")   # seat 3 calls 20
    engine.step("allin")  # seat 0 to 35 (short)
    engine.step("allin")  # seat 1 to 50 (short again, but 30 over seat 3's call)
    engine.step("call")   # seat 2 calls 50

    assert engine.current_actor == 3
    assert ActionType.RAISE in legal_types(engine)


def test_full_raise_reopens_raising():
    engine = PokerEngine(num_players=3, blind_amount=10, starting_stack=1000)
    engine.game.dealer_index = 0
    engine.start_hand()

    engine.step("call")       # seat 0
    engine.step("raise 60")   # seat 1, full raise
    engine.step("call")       # seat 2

    assert engine.current_actor == 0
    assert ActionType.RAISE in legal_types(engine)


def test_no_raise_when_nobody_can_respond():
    engine = PokerEngine(num_players=2, blind_amount=10, starting_stack=1000)
    engine.game.players[1].chips = 50
    engine.game.dealer_index = 0
    engine.start_hand()

    engine.step("call")   # dealer completes to 20
    engine.step("allin")  # seat 1 all-in to 50

    assert legal_types(engine) == {ActionType.FOLD, ActionType.CALL}


def test_raise_string_means_raise_to():
    engine = PokerEngine(num_players=2, blind_amount=20, starting_stack=500)
    engine.start_hand()
    actor = engine.game.players[engine.current_actor]

    engine.step("raise 100")

    assert actor.bet == 100
    assert engine.current_bet == 100


def test_raise_below_minimum_is_rejected_without_changing_state():
    engine = PokerEngine(num_players=2, blind_amount=20, starting_stack=500)
    engine.start_hand()
    actor = engine.game.players[engine.current_actor]

    with pytest.raises(ValueError, match="at least 80"):
        engine.step(Action.raise_to(50))
    assert actor.bet == 20


def test_step_hand_conserves_chips_with_passive_actions():
    engine = PokerEngine(num_players=4, blind_amount=20, starting_stack=500)
    before = total_chips(engine)
    engine.start_hand()

    guard = 0
    while not engine.hand_over:
        guard += 1
        assert guard < 200
        legal = engine.legal_actions()
        passive = [a for a in legal if a.action_type in (ActionType.CHECK, ActionType.CALL)]
        engine.step(passive[0] if passive else legal[0])

    assert total_chips(engine) == before
    assert engine.last_winners


def test_all_in_side_pots_conserve_chips():
    engine = PokerEngine(num_players=3, blind_amount=10, starting_stack=0)
    for player, stack in zip(engine.game.players, [10, 30, 60]):
        player.chips = stack
    engine.game.dealer_index = 2
    before = total_chips(engine)
    engine.start_hand()

    while not engine.hand_over:
        engine.step(Action.all_in())

    assert total_chips(engine) == before


def test_many_random_hands_conserve_chips():
    from providers import random_choice_provider

    engine = PokerEngine(num_players=6, blind_amount=10, starting_stack=300)
    engine.set_global_action_provider(random_choice_provider)
    before = total_chips(engine)
    for _ in range(200):
        if len(engine.game.players_with_chips()) < 2:
            break
        engine.run()
        assert total_chips(engine) == before
        assert [p.seat for p in engine.game.players] == list(range(6))


def test_folded_hands_stay_hidden_but_showdown_hands_are_revealed():
    engine = PokerEngine(num_players=3, blind_amount=10, starting_stack=500)
    engine.game.dealer_index = 0
    engine.start_hand()
    engine.step("fold")  # seat 0 folds preflop
    while not engine.hand_over:
        engine.step("call")

    state = engine.public_state_for(1)
    assert state["players"][0]["hand"] == []
    assert state["players"][2]["hand"] and state["players"][2]["hand_name"]
    assert engine.went_to_showdown
    assert sum(r["won"] for r in state["results"]) == 40  # both blinds, nothing from the folder


def test_uncontested_winner_does_not_show_cards():
    engine = PokerEngine(num_players=2, blind_amount=10, starting_stack=500)
    engine.start_hand()
    folder = engine.current_actor
    engine.step("fold")

    state = engine.public_state_for(folder)
    winner = 1 - folder
    assert state["players"][winner]["hand"] == []
    assert state["results"] == [
        {"seat": winner, "won": 30, "hand_name": None, "description": None, "best_cards": None, "decided_by": None},
    ]


def test_showdown_explains_a_kicker_win_and_shows_both_hands():
    engine = PokerEngine(num_players=2, blind_amount=10, starting_stack=500)
    engine.start_hand()
    engine.game.players[0].hand = cards("AS 3H")
    engine.game.players[1].hand = cards("QD 5H")
    # Draws pop off the end: burn, flop, burn, turn, burn, river.
    engine.game.deck.cards = cards("2C 4D KC 4C 7D 7H 7S 4H")
    while not engine.hand_over:
        engine.step("call")

    state = engine.public_state_for(0)
    [result] = state["results"]
    assert result["seat"] == 0
    assert result["description"] == "Three of a Kind, Sevens"
    assert result["decided_by"] == "Ace kicker"
    loser = state["players"][1]
    assert loser["hand_description"] == "Three of a Kind, Sevens"
    assert [c.rank.value for c in loser["best_cards"]] == [7, 7, 7, 13, 12]
