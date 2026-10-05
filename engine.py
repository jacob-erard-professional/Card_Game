from __future__ import annotations

import logging
from typing import Callable, Dict, Optional

from actions.action import Action, ActionType, parse_action
from actions.dealing import deal_board, deal_hole_cards
from actions.showdown import award_pot, best_five, describe_hand, evaluate_hand, hand_name, kicker_decided
from models.game import PokerState
from models.player import Player
from providers import console_provider

logger = logging.getLogger(__name__)

MAX_PLAYERS = 22

# A provider decides the given player's move; it may return an Action or an action string.
ActionProvider = Callable[["PokerEngine", Player], "Action | str"]


class PokerEngine:
    """Stepable no-limit hold'em engine.

    Raise amounts are always the player's total bet for the current street ("raise to").
    """

    def __init__(self, num_players: int = 3, blind_amount: int = 20, starting_stack: int = 1000):
        if not 2 <= num_players <= MAX_PLAYERS:
            raise ValueError(f"num_players must be between 2 and {MAX_PLAYERS}")

        players = [Player(seat=i, chips=starting_stack) for i in range(num_players)]
        self.game = PokerState(blind_amount=blind_amount, players=players)
        self.action_providers: Dict[int, ActionProvider] = {}

        self.hand_started = False
        self.hand_over = False
        self.current_bet = 0
        self.min_raise = blind_amount * 2
        self.current_actor: Optional[int] = None
        self.has_acted: Dict[int, bool] = {}
        # The bet each player last acted facing. A player who has acted may only
        # raise again once the bet has grown by a full raise since then, so a
        # short all-in does not reopen betting for them.
        self.acted_at_bet: Dict[int, int] = {}
        self.starting_stacks: Dict[int, int] = {}
        self.last_winners: list[Player] = []
        # Every blind and action this hand, in order: {"seat", "phase", "action", "total_bet", "raised"}.
        self.action_log: list[dict] = []
        # Board size when the hand became an all-in runout with no decisions left, else None.
        self.runout_from: Optional[int] = None
        # Set when a hand ends: whether it reached showdown, and per winner
        # {"seat", "won", "hand_name", "description", "best_cards", "decided_by"} (hand details only at showdown;
        # decided_by names the kicker when that alone beat the best losing hand).
        self.went_to_showdown = False
        self.hand_results: list[dict] = []

    def set_action_providers(self, providers: Dict[int, ActionProvider]) -> None:
        self.action_providers = dict(providers)

    def set_global_action_provider(self, provider: ActionProvider) -> None:
        self.action_providers = {p.seat: provider for p in self.game.players}

    def set_action_provider(self, seat: int, provider: ActionProvider) -> None:
        self.action_providers[seat] = provider

    def blind_positions(self) -> tuple[int, int]:
        """Return (small blind seat, big blind seat), skipping busted seats.

        Heads-up, the dealer posts the small blind.
        """
        game = self.game
        dealer = game.dealer_index
        if len(game.players_with_chips()) == 2:
            return dealer, game.next_seat_with_chips(dealer)
        small = game.next_seat_with_chips(dealer)
        return small, game.next_seat_with_chips(small)

    def start_hand(self) -> None:
        """Start a hand and stop before the first player's preflop decision."""
        if len(self.game.players_with_chips()) < 2:
            raise ValueError("At least two players with chips are required")
        if self.game.players[self.game.dealer_index].chips == 0:
            self.game.advance_dealer()

        self.game.reset_round_state()
        self.game.phase = "preflop"
        deal_hole_cards(self.game)
        self.starting_stacks = {p.seat: p.chips for p in self.game.players}
        self.last_winners = []
        self.action_log = []
        self.runout_from = None
        self.went_to_showdown = False
        self.hand_results = []
        self.hand_started = True
        self.hand_over = False

        small_idx, big_idx = self.blind_positions()
        for idx, amount in ((small_idx, self.game.blind_amount), (big_idx, self.game.blind_amount * 2)):
            player = self.game.players[idx]
            self._post_amount(player, amount)
            self.action_log.append({
                "seat": player.seat, "phase": "preflop", "action": "post",
                "total_bet": player.bet, "raised": False,
            })

        self.current_bet = max(p.bet for p in self.game.players)
        self.min_raise = self.game.blind_amount * 2
        self._reset_street_actions()
        self.current_actor = self._next_actor((big_idx + 1) % len(self.game.players))
        if self._betting_complete():
            self._finish_street_or_hand()

    def run(self) -> list[Player]:
        """Play a full hand using the configured action providers, then advance to the next hand."""
        self.start_hand()
        guard = 0
        while not self.hand_over:
            guard += 1
            if guard > 1000:
                raise RuntimeError("Hand did not terminate after 1000 actions")

            player = self.game.players[self.current_actor]
            provider = self.action_providers.get(player.seat, console_provider)
            self.step(self._provider_action(provider, player))

        winners = self.last_winners
        self.next_round()
        return winners

    def raise_bounds(self, seat: Optional[int] = None) -> Optional[tuple[int, int]]:
        """Return (min, max) legal raise-to totals for the current actor, or None if they cannot raise."""
        if not self._can_act(seat) or not self._raising_open():
            return None
        player = self.game.players[self.current_actor]
        min_total = self.current_bet + self.min_raise
        max_total = player.bet + player.chips
        if max_total < min_total:
            return None
        return min_total, max_total

    def legal_actions(self, seat: Optional[int] = None) -> list[Action]:
        """Return legal actions for the current actor. A raise entry carries the minimum raise-to total."""
        if not self._can_act(seat):
            return []

        player = self.game.players[self.current_actor]
        actions = [Action.fold()]
        actions.append(Action.check() if player.bet == self.current_bet else Action.call())
        # Going all-in for no more than a call is always allowed; going all-in for more is a raise.
        if player.bet + player.chips <= self.current_bet or self._raising_open():
            actions.append(Action.all_in())

        bounds = self.raise_bounds(seat)
        if bounds is not None:
            actions.append(Action.raise_to(bounds[0]))
        return actions

    def step(self, action: Action | str) -> dict:
        """Apply one legal action for the current actor and advance the hand.

        Raises ValueError if the action is illegal; the state is left unchanged.
        """
        if not self.hand_started:
            self.start_hand()
        if self.hand_over or self.current_actor is None:
            raise RuntimeError("Cannot step a completed hand")

        actor_idx = self.current_actor
        player = self.game.players[actor_idx]
        action = self._coerce_action(action)
        self._validate_action(player, action)
        bet_before = self.current_bet
        self._apply_action(player, action)
        self.action_log.append({
            "seat": player.seat,
            "phase": self.game.phase,
            "action": action.action_type.value,
            "total_bet": player.bet,
            "raised": self.current_bet > bet_before,
        })
        self.has_acted[player.seat] = True
        self.acted_at_bet[player.seat] = self.current_bet

        active = [p for p in self.game.players if p.in_hand]
        if len(active) == 1:
            self._resolve_current_hand()
        elif self._betting_complete():
            self._finish_street_or_hand()
        else:
            self.current_actor = self._next_actor((actor_idx + 1) % len(self.game.players))

        return {
            "state": self.game,
            "current_player": self.current_actor,
            "terminal": self.hand_over,
            "winners": self.last_winners,
            "chip_deltas": self.chip_deltas() if self.hand_over else {},
        }

    def chip_deltas(self) -> Dict[int, int]:
        return {
            p.seat: p.chips - self.starting_stacks.get(p.seat, p.chips)
            for p in self.game.players
        }

    def public_state_for(self, seat: int) -> dict:
        """Return UI-safe state. Opponents' hole cards stay hidden unless they are shown down."""
        players = []
        for player in self.game.players:
            shown = player.seat == seat or self._shown_down(player)
            players.append({
                "seat": player.seat,
                "name": player.name,
                "chips": player.chips,
                "bet": player.bet,
                "committed": player.committed,
                "folded": player.folded,
                "all_in": player.all_in,
                "sitting_out": player.sitting_out,
                "hand": player.hand if shown else [],
                "hand_name": self._hand_name(player) if self._shown_down(player) else None,
                "hand_description": describe_hand(self._rank(player)) if self._shown_down(player) else None,
                "best_cards": best_five(player.hand + self.game.community_cards) if self._shown_down(player) else None,
            })

        return {
            "phase": self.game.phase,
            "pot": self.game.pot,
            "community_cards": self.game.community_cards,
            "dealer_index": self.game.dealer_index,
            "current_player": self.current_actor,
            "current_bet": self.current_bet,
            "min_raise": self.min_raise,
            "players": players,
            "legal_actions": self.legal_actions(seat),
            "terminal": self.hand_over,
            "winners": [p.seat for p in self.last_winners],
            "results": list(self.hand_results),
            "action_log": list(self.action_log),
        }

    def next_round(self) -> None:
        """Clear per-hand engine state and move the button. Busted players keep their seat."""
        self.hand_started = False
        self.hand_over = False
        self.current_actor = None
        self.current_bet = 0
        self.has_acted = {}
        self.acted_at_bet = {}
        self.last_winners = []
        self.game.advance_dealer()

    def _can_act(self, seat: Optional[int]) -> bool:
        if not self.hand_started or self.hand_over or self.current_actor is None:
            return False
        player = self.game.players[self.current_actor]
        if seat is not None and player.seat != seat:
            return False
        return player.in_hand and not player.all_in and player.chips > 0

    def _raising_open(self) -> bool:
        """Whether the current actor may raise: someone must be left to respond, and if the
        actor has already acted this street the bet must have grown by a full raise since."""
        actor = self.game.players[self.current_actor]
        others_can_respond = any(
            p.in_hand and not p.all_in and p.chips > 0 and p is not actor
            for p in self.game.players
        )
        if not others_can_respond:
            return False
        acted_at = self.acted_at_bet.get(actor.seat)
        return acted_at is None or self.current_bet - acted_at >= self.min_raise

    def _post_amount(self, player: Player, amount: int) -> int:
        actual = min(max(0, amount), player.chips)
        player.chips -= actual
        self.game.pot += actual
        player.bet += actual
        player.committed += actual
        player.all_in = player.chips == 0
        return actual

    def _coerce_action(self, action: Action | str) -> Action:
        parsed = parse_action(action)
        if parsed.action_type == ActionType.CALL and self.current_actor is not None:
            if self.current_bet == self.game.players[self.current_actor].bet:
                return Action.check()
        return parsed

    def _validate_action(self, player: Player, action: Action) -> None:
        legal_types = {item.action_type for item in self.legal_actions(player.seat)}
        if action.action_type not in legal_types:
            raise ValueError(f"Illegal action {action.action_type.value} for player {player.seat}")

        if action.action_type == ActionType.RAISE:
            if action.amount is None:
                raise ValueError("Raise requires a total bet amount")
            min_total, max_total = self.raise_bounds(player.seat)
            if action.amount < min_total:
                raise ValueError(f"Raise total must be at least {min_total}")
            if action.amount > max_total:
                raise ValueError(f"Raise total cannot exceed {max_total}")

    def _apply_action(self, player: Player, action: Action) -> None:
        if action.action_type == ActionType.FOLD:
            player.folded = True
            return

        if action.action_type == ActionType.CHECK:
            return

        if action.action_type == ActionType.CALL:
            self._post_amount(player, self.current_bet - player.bet)
            return

        if action.action_type == ActionType.ALL_IN:
            self._post_amount(player, player.chips)
            if player.bet > self.current_bet:
                raise_size = player.bet - self.current_bet
                self.current_bet = player.bet
                if raise_size >= self.min_raise:
                    self.min_raise = raise_size
                    self._reset_acted_after_raise(player.seat)
            return

        if action.action_type == ActionType.RAISE:
            self._post_amount(player, action.amount - player.bet)
            raise_size = player.bet - self.current_bet
            self.current_bet = player.bet
            self.min_raise = max(self.min_raise, raise_size)
            self._reset_acted_after_raise(player.seat)

    def _reset_street_actions(self) -> None:
        self.has_acted = {p.seat: False for p in self.game.players}
        self.acted_at_bet = {}

    def _reset_acted_after_raise(self, raiser_num: int) -> None:
        self.has_acted = {p.seat: False for p in self.game.players}
        self.has_acted[raiser_num] = True

    def _next_actor(self, start_idx: int) -> Optional[int]:
        for offset in range(len(self.game.players)):
            idx = (start_idx + offset) % len(self.game.players)
            player = self.game.players[idx]
            if player.in_hand and not player.all_in and player.chips > 0:
                return idx
        return None

    def _betting_complete(self) -> bool:
        active = [p for p in self.game.players if p.in_hand]
        actors = [p for p in active if not p.all_in and p.chips > 0]
        if len(active) <= 1 or not actors:
            return True
        # A lone player who already matches the bet has nobody left to act against.
        if len(actors) == 1 and actors[0].bet >= self.current_bet:
            return True
        return all(self.has_acted.get(p.seat, False) and p.bet == self.current_bet for p in actors)

    def _finish_street_or_hand(self) -> None:
        if self.runout_from is None and self.game.phase != "river" and self._all_in_locked():
            self.runout_from = len(self.game.community_cards)
        if self.game.phase == "preflop":
            deal_board(self.game, 3)
            self._start_postflop_street("flop")
        elif self.game.phase == "flop":
            deal_board(self.game, 1)
            self._start_postflop_street("turn")
        elif self.game.phase == "turn":
            deal_board(self.game, 1)
            self._start_postflop_street("river")
        else:
            self._resolve_current_hand()

    def _all_in_locked(self) -> bool:
        """At least two players are still in, but at most one of them can still bet."""
        live = [p for p in self.game.players if p.in_hand]
        can_bet = [p for p in live if not p.all_in and p.chips > 0]
        return len(live) >= 2 and len(can_bet) <= 1

    def _start_postflop_street(self, phase: str) -> None:
        self.game.phase = phase
        for player in self.game.players:
            player.bet = 0
        self.current_bet = 0
        self.min_raise = self.game.blind_amount * 2
        self._reset_street_actions()
        self.current_actor = self._next_actor((self.game.dealer_index + 1) % len(self.game.players))
        if self._betting_complete():
            self._finish_street_or_hand()

    def _shown_down(self, player: Player) -> bool:
        return self.hand_over and self.went_to_showdown and player.in_hand

    def _rank(self, player: Player) -> tuple:
        return evaluate_hand(player.hand + self.game.community_cards)

    def _hand_name(self, player: Player) -> str:
        return hand_name(self._rank(player))

    def _decided_by(self, winner: Player) -> str | None:
        losers = [self._rank(p) for p in self.game.players if p.in_hand and p not in self.last_winners]
        return kicker_decided(self._rank(winner), max(losers)) if losers else None

    def _resolve_current_hand(self) -> None:
        self.went_to_showdown = sum(1 for p in self.game.players if p.in_hand) >= 2
        chips_before = {p.seat: p.chips for p in self.game.players}
        self.last_winners = award_pot(self.game)
        shown = self.went_to_showdown
        self.hand_results = [
            {
                "seat": p.seat,
                "won": p.chips - chips_before[p.seat],
                "hand_name": self._hand_name(p) if shown else None,
                "description": describe_hand(self._rank(p)) if shown else None,
                "best_cards": best_five(p.hand + self.game.community_cards) if shown else None,
                "decided_by": self._decided_by(p) if shown else None,
            }
            for p in self.last_winners
        ]
        self.hand_over = True
        self.current_actor = None

    def _provider_action(self, provider: ActionProvider, player: Player) -> Action:
        last_error = None
        for _ in range(50):
            try:
                action = self._coerce_action(provider(self, player))
                self._validate_action(player, action)
                return action
            except ValueError as exc:
                last_error = exc
                logger.warning("Invalid action from player %s: %s", player.seat, exc)
        raise ValueError(f"Provider returned no legal action for player {player.seat}: {last_error}")
