from __future__ import annotations

from typing import Callable, Dict, Optional

from actions.action import Action, ActionType, parse_action
import actions.dealing as dealing
from actions.betting import BettingManager
from actions.showdown import ShowdownManager
from models.card import Deck
from models.chip import ChipHolder
from models.game import PokerState
from models.player import Player


class PokerEngine:
    """Stepable poker engine with provider compatibility for automated play."""

    def __init__(
        self,
        num_players: int = 3,
        blind_amount: int = 20,
        chip_breakdown: Optional[dict] = None,
        denominations: Optional[list] = None,
    ):
        if chip_breakdown is None:
            chip_breakdown = {5: 100, 25: 40, 100: 20}
        if denominations is None:
            denominations = [5, 25, 100]
        if 1 not in denominations:
            denominations = [1] + list(denominations)
        if num_players > 22:
            raise ValueError("Too many players")

        self.chip_breakdown = chip_breakdown
        self.denominations = denominations
        self.game = self._initialize_game(num_players, blind_amount, chip_breakdown, denominations)
        setattr(self.game, "_engine", self)
        self.action_providers: Optional[Dict[int, Callable[[PokerState, Player], str]]] = None
        self.betting_manager = BettingManager(self.game, self.action_providers)
        self.showdown_manager = ShowdownManager(self.game, self.action_providers)
        self.players_to_add = []

        self.hand_started = False
        self.hand_over = False
        self.current_bet = 0
        self.min_raise = blind_amount * 2
        self.current_actor: Optional[int] = None
        self.has_acted: Dict[int, bool] = {}
        self.starting_stacks: Dict[int, int] = {}
        self.last_winners: list[Player] = []

    def set_action_providers(self, providers: Dict[int, Callable[[PokerState, Player], str]]):
        """Set custom action providers for networked/AI play."""
        self.action_providers = providers
        self.betting_manager.action_providers = providers
        self.showdown_manager.action_providers = providers

    def set_global_action_provider(self, provider: Callable[[PokerState, Player], str]):
        providers = {p.player_num: provider for p in self.game.players}
        self.set_action_providers(providers)

    def add_action_provider(self, player_num: int, provider: Callable[[PokerState, Player], str]):
        if self.action_providers is None:
            self.action_providers = {}
        self.action_providers[player_num] = provider
        self.betting_manager.action_providers = self.action_providers
        self.showdown_manager.action_providers = self.action_providers

    def set_player_action_provider(self, player_num: int, provider: Callable[[PokerState, Player], str]):
        self.add_action_provider(player_num, provider)

    def preflop_betting_round(self):
        return self.betting_manager.preflop_betting_round()

    def postflop_betting_round(self):
        return self.betting_manager.postflop_betting_round()

    def start_hand(self) -> None:
        """Start a hand and stop before the first player's preflop decision."""
        if len(self.game.players) < 2:
            raise ValueError("At least two players are required")

        self.game.reset_round_state()
        self.game.phase = "preflop"
        self.deal()
        self.starting_stacks = {p.player_num: p.chips.total() for p in self.game.players}
        self.last_winners = []
        self.hand_started = True
        self.hand_over = False

        num_players = len(self.game.players)
        small_idx = (self.game.dealer_index + 1) % num_players
        big_idx = (self.game.dealer_index + 2) % num_players
        self._post_amount(self.game.players[small_idx], self.game.blind_amount)
        self._post_amount(self.game.players[big_idx], self.game.blind_amount * 2)

        self.current_bet = max((p.bet for p in self.game.players), default=0)
        self.min_raise = self.game.blind_amount * 2
        self.has_acted = {p.player_num: False for p in self.game.players}
        self.current_actor = self._next_actor((big_idx + 1) % num_players)
        self.game.current_player = self.current_actor if self.current_actor is not None else 0

    def run(self):
        """Run a full hand using configured action providers."""
        self.start_hand()
        providers = self._get_step_providers()

        guard = 0
        while not self.hand_over:
            guard += 1
            if guard > 1000:
                raise RuntimeError("Hand did not terminate after 1000 actions")

            player = self.game.players[self.current_actor]
            provider = providers[player.player_num]
            action = self._provider_action(provider, player)
            self.step(action)

        winners = self.last_winners
        self.next_round()
        return winners

    def legal_actions(self, player_num: Optional[int] = None) -> list[Action]:
        """Return legal actions for the current actor.

        Raise amounts are expressed as the player's total bet for the current street.
        """
        if not self.hand_started or self.hand_over or self.current_actor is None:
            return []

        player = self.game.players[self.current_actor]
        if player_num is not None and player.player_num != player_num:
            return []
        if player.folded or player.all_in or player.chips.total() <= 0:
            return []

        amount_to_call = max(0, self.current_bet - player.bet)
        stack = player.chips.total()
        actions = [Action.fold()]

        if amount_to_call == 0:
            actions.append(Action.check())
        else:
            actions.append(Action.call())

        actions.append(Action.all_in())

        max_total_bet = player.bet + stack
        min_total_bet = self.current_bet + self.min_raise
        if max_total_bet >= min_total_bet:
            actions.append(Action.raise_to(min_total_bet))

        return actions

    def legal_action_mask(self, player_num: Optional[int] = None) -> list[bool]:
        """Mask for DQN actions: fold, check/call, half-pot raise, pot raise, all-in."""
        action_types = {action.action_type for action in self.legal_actions(player_num)}
        can_raise = ActionType.RAISE in action_types
        return [
            ActionType.FOLD in action_types,
            ActionType.CHECK in action_types or ActionType.CALL in action_types,
            can_raise,
            can_raise,
            ActionType.ALL_IN in action_types,
        ]

    def step(self, action: Action | str) -> dict:
        """Apply one legal action for the current actor and advance the hand."""
        if not self.hand_started:
            self.start_hand()
        if self.hand_over or self.current_actor is None:
            raise RuntimeError("Cannot step a completed hand")

        actor_idx = self.current_actor
        player = self.game.players[actor_idx]
        action = self._coerce_action(action, raw_string=isinstance(action, str))
        self._validate_action(player, action)
        self._apply_action(player, action)
        self.has_acted[player.player_num] = True

        active = [p for p in self.game.players if not p.folded]
        if len(active) == 1:
            self._resolve_current_hand()
        elif self._betting_complete():
            self._finish_street_or_hand()
        else:
            self.current_actor = self._next_actor((actor_idx + 1) % len(self.game.players))
            self.game.current_player = self.current_actor if self.current_actor is not None else 0

        return {
            "state": self.game,
            "current_player": self.current_actor,
            "terminal": self.hand_over,
            "winners": self.last_winners,
            "chip_deltas": self.chip_deltas() if self.hand_over else {},
        }

    def showdown(self) -> list:
        return self.showdown_manager.execute_showdown()

    def chip_deltas(self) -> Dict[int, int]:
        return {
            p.player_num: p.chips.total() - self.starting_stacks.get(p.player_num, p.chips.total())
            for p in self.game.players
        }

    def public_state_for(self, player_num: int) -> dict:
        """Return UI-safe state with opponent hole cards hidden until terminal."""
        players = []
        for player in self.game.players:
            players.append({
                "player_num": player.player_num,
                "name": player.name,
                "chips": player.chips.total(),
                "bet": player.bet,
                "committed": player.committed,
                "folded": player.folded,
                "all_in": player.all_in,
                "hand": player.hand if player.player_num == player_num or self.hand_over else [],
            })

        return {
            "phase": self.game.phase,
            "pot": self.game.pot.total(),
            "community_cards": self.game.community_cards,
            "dealer_index": self.game.dealer_index,
            "current_player": self.current_actor,
            "current_bet": self.current_bet,
            "min_raise": self.min_raise,
            "players": players,
            "legal_actions": self.legal_actions(player_num),
            "terminal": self.hand_over,
            "winners": [p.player_num for p in self.last_winners],
        }

    def next_round(self):
        self.game.reset_round_state()
        self.hand_started = False
        self.hand_over = False
        self.current_actor = None
        self.current_bet = 0
        self.has_acted = {}
        self.last_winners = []

        self.game.remove_broke_players()
        self.game.advance_dealer()
        if len(self.game.deck.cards) < 20:
            self.game.deck = Deck()

    def flop(self):
        dealing.flop(self.game)

    def turn(self):
        dealing.turn(self.game)

    def river(self):
        dealing.river(self.game)

    def deal(self):
        dealing.deal(self.game)

    def add_player(self, name):
        return

    def _initialize_game(
        self,
        num_players: int,
        blind_amount: int,
        chip_breakdown: dict,
        denominations: list,
    ) -> PokerState:
        players = []
        for i in range(num_players):
            players.append(Player(player_num=i, chips=ChipHolder(chip_breakdown, denominations)))

        return PokerState(
            blind_amount=blind_amount,
            players=players,
            community_cards=[],
            burn_cards=[],
            pot=ChipHolder(denominations=denominations),
            dealer_index=0,
            current_player=1,
            deck=Deck(),
            phase="preflop",
        )

    def _post_amount(self, player: Player, amount: int) -> int:
        actual = min(max(0, amount), player.chips.total())
        if actual <= 0:
            return 0
        player.chips.transfer_to(self.game.pot, actual)
        player.bet += actual
        player.committed += actual
        player.all_in = player.chips.total() == 0
        return actual

    def _coerce_action(self, action: Action | str, raw_string: bool) -> Action:
        parsed = parse_action(action)
        if parsed.action_type == ActionType.CALL and self.current_actor is not None:
            player = self.game.players[self.current_actor]
            if self.current_bet == player.bet:
                return Action.check()
        if raw_string and parsed.action_type == ActionType.RAISE:
            raise_by = parsed.amount or 0
            return Action.raise_to(self.current_bet + raise_by)
        return parsed

    def _validate_action(self, player: Player, action: Action) -> None:
        legal_types = {item.action_type for item in self.legal_actions(player.player_num)}
        if action.action_type not in legal_types:
            raise ValueError(f"Illegal action {action.action_type.value} for player {player.player_num}")

        if action.action_type == ActionType.RAISE:
            if action.amount is None:
                raise ValueError("Raise requires a total bet amount")
            max_total_bet = player.bet + player.chips.total()
            min_total_bet = self.current_bet + self.min_raise
            if action.amount < min_total_bet:
                raise ValueError(f"Raise total must be at least {min_total_bet}")
            if action.amount > max_total_bet:
                raise ValueError(f"Raise total cannot exceed {max_total_bet}")

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
            self._post_amount(player, player.chips.total())
            if player.bet > self.current_bet:
                raise_size = player.bet - self.current_bet
                self.current_bet = player.bet
                if raise_size >= self.min_raise:
                    self.min_raise = raise_size
                    self._reset_acted_after_raise(player.player_num)
            return

        if action.action_type == ActionType.RAISE:
            self._post_amount(player, action.amount - player.bet)
            raise_size = player.bet - self.current_bet
            self.current_bet = player.bet
            self.min_raise = max(self.min_raise, raise_size)
            self._reset_acted_after_raise(player.player_num)

    def _reset_acted_after_raise(self, raiser_num: int) -> None:
        self.has_acted = {p.player_num: False for p in self.game.players}
        self.has_acted[raiser_num] = True

    def _next_actor(self, start_idx: int) -> Optional[int]:
        if not self.game.players:
            return None
        for offset in range(len(self.game.players)):
            idx = (start_idx + offset) % len(self.game.players)
            player = self.game.players[idx]
            if not player.folded and not player.all_in and player.chips.total() > 0:
                return idx
        return None

    def _betting_complete(self) -> bool:
        active = [p for p in self.game.players if not p.folded]
        actors = [p for p in active if not p.all_in and p.chips.total() > 0]
        if len(active) <= 1 or not actors:
            return True
        return all(self.has_acted.get(p.player_num, False) and p.bet == self.current_bet for p in actors)

    def _finish_street_or_hand(self) -> None:
        if self.game.phase == "preflop":
            self.flop()
            self._start_postflop_street("flop")
        elif self.game.phase == "flop":
            self.turn()
            self._start_postflop_street("turn")
        elif self.game.phase == "turn":
            self.river()
            self._start_postflop_street("river")
        else:
            self._resolve_current_hand()

    def _start_postflop_street(self, phase: str) -> None:
        self.game.phase = phase
        for player in self.game.players:
            player.bet = 0
        self.current_bet = 0
        self.min_raise = self.game.blind_amount * 2
        self.has_acted = {p.player_num: False for p in self.game.players}
        self.current_actor = self._next_actor((self.game.dealer_index + 1) % len(self.game.players))
        self.game.current_player = self.current_actor if self.current_actor is not None else 0
        if self._betting_complete():
            self._finish_street_or_hand()

    def _resolve_current_hand(self) -> None:
        self.last_winners = self.showdown()
        self.hand_over = True
        self.current_actor = None
        self.game.current_player = 0

    def _get_step_providers(self) -> Dict[int, Callable[[PokerState, Player], str]]:
        if self.action_providers is None:
            provider = self.betting_manager._get_console_provider()
            return {p.player_num: provider for p in self.game.players}

        providers = dict(self.action_providers)
        console_provider = self.betting_manager._get_console_provider()
        for player in self.game.players:
            providers.setdefault(player.player_num, console_provider)
        return providers

    def _provider_action(self, provider: Callable[[PokerState, Player], str], player: Player) -> Action:
        last_error = None
        for _ in range(50):
            raw_action = provider(self.game, player)
            try:
                action = self._coerce_action(raw_action, raw_string=isinstance(raw_action, str))
                self._validate_action(player, action)
                return action
            except ValueError as exc:
                last_error = exc
                print(f"Invalid action: {exc}")
        raise ValueError(f"Provider returned no legal action for player {player.player_num}: {last_error}")


def initialize_game(
    num_players: int,
    blind_amount: int,
    chip_breakdown: dict,
    denominations: list,
) -> PokerState:
    pe = PokerEngine(
        num_players=num_players,
        blind_amount=blind_amount,
        chip_breakdown=chip_breakdown,
        denominations=denominations,
    )
    return pe.game
