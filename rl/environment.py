from __future__ import annotations

import random
from dataclasses import dataclass
from contextlib import redirect_stdout
from io import StringIO

from engine import PokerEngine
from rl.actions import action_from_index
from rl.encoding import observation_vector


@dataclass
class StepResult:
    observation: list[float]
    reward: float
    terminal: bool
    mask: list[bool]
    info: dict


class PokerRLEnv:
    """Single-controlled-player environment with automated random opponents."""

    def __init__(
        self,
        num_players: int = 2,
        controlled_player: int = 0,
        blind_amount: int = 20,
        chip_breakdown: dict | None = None,
        max_players: int = 6,
        random_dealer: bool = True,
        quiet: bool = True,
    ):
        self.num_players = num_players
        self.controlled_player = controlled_player
        self.blind_amount = blind_amount
        self.chip_breakdown = chip_breakdown
        self.max_players = max_players
        self.random_dealer = random_dealer
        self.quiet = quiet
        self.engine: PokerEngine | None = None

    def reset(self) -> tuple[list[float], list[bool]]:
        self.engine = PokerEngine(
            num_players=self.num_players,
            blind_amount=self.blind_amount,
            chip_breakdown=self.chip_breakdown,
        )
        if self.random_dealer:
            self.engine.game.dealer_index = random.randrange(self.num_players)
        self.engine.start_hand()
        self._play_until_controlled_or_terminal()
        return self.observation(), self.mask()

    def step(self, action_index: int) -> StepResult:
        if self.engine is None:
            self.reset()
        if self.engine.hand_over:
            return StepResult(self.observation(), 0.0, True, self.mask(), {})

        if self.engine.current_actor != self.controlled_player:
            self._play_until_controlled_or_terminal()

        if not self.engine.hand_over:
            self._step_engine(action_from_index(self.engine, action_index))
            self._play_until_controlled_or_terminal()

        reward = 0.0
        if self.engine.hand_over:
            reward = self.engine.chip_deltas().get(self.controlled_player, 0) / max(1, self.blind_amount)

        return StepResult(
            observation=self.observation(),
            reward=reward,
            terminal=self.engine.hand_over,
            mask=self.mask(),
            info={"winners": [p.player_num for p in self.engine.last_winners]},
        )

    def observation(self) -> list[float]:
        return observation_vector(self.engine, self.controlled_player, self.max_players)

    def mask(self) -> list[bool]:
        return self.engine.legal_action_mask(self.controlled_player)

    def _play_until_controlled_or_terminal(self) -> None:
        guard = 0
        while not self.engine.hand_over and self.engine.current_actor != self.controlled_player:
            guard += 1
            if guard > 1000:
                raise RuntimeError("Opponent automation did not terminate")
            legal = self.engine.legal_actions()
            action = self._opponent_action(legal)
            self._step_engine(action)

    def _opponent_action(self, legal):
        weighted = []
        for action in legal:
            if action.action_type.value in ("check", "call"):
                weighted.extend([action] * 5)
            elif action.action_type.value == "raise":
                weighted.extend([action] * 3)
            elif action.action_type.value == "allin":
                weighted.append(action)
            elif action.action_type.value == "fold":
                weighted.append(action)
        return random.choice(weighted or legal)

    def _step_engine(self, action) -> None:
        if self.quiet:
            with redirect_stdout(StringIO()):
                self.engine.step(action)
        else:
            self.engine.step(action)
