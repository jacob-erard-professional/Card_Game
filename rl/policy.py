"""Load a trained average policy and play it through the engine."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from actions.action import Action
from rl.actions import action_from_index, legal_action_mask
from rl.encoding import observation_vector
from rl.nfsp import masked_logits, mlp

CHECKPOINT_DIR = Path(__file__).resolve().parent / "checkpoints"


def checkpoint_path(num_players: int) -> Path:
    return CHECKPOINT_DIR / f"rl_{num_players}p.pt"


class PolicyBot:
    """The deployable NFSP average policy for one table size. Samples its actions, so it mixes.

    It can also play smaller tables than it trained for; missing seats look like busted players.
    """

    def __init__(self, network: torch.nn.Module, num_players: int, payouts: list[float], seed: int | None = None):
        self.network = network.eval()
        self.num_players = num_players
        self.payouts = payouts
        self.rng = np.random.default_rng(seed)

    @classmethod
    def load(cls, path: str | Path, seed: int | None = None) -> "PolicyBot":
        checkpoint = torch.load(path, map_location="cpu")
        meta = checkpoint["meta"]
        network = mlp(meta["obs_size"], meta["hidden"])
        network.load_state_dict(checkpoint["policy"])
        return cls(network, meta["num_players"], meta["payouts"], seed)

    def action_probabilities(self, engine, seat: int) -> np.ndarray:
        obs = torch.from_numpy(observation_vector(engine, seat, self.payouts, self.num_players)).unsqueeze(0)
        mask = torch.from_numpy(legal_action_mask(engine)).unsqueeze(0)
        with torch.no_grad():
            return F.softmax(masked_logits(self.network(obs), mask), dim=1)[0].numpy()

    def act(self, engine, seat: int) -> Action:
        probs = self.action_probabilities(engine, seat)
        index = int(self.rng.choice(len(probs), p=probs / probs.sum()))
        return action_from_index(engine, index)

    def __call__(self, engine, player) -> Action:
        """Use the bot directly as an engine action provider."""
        return self.act(engine, player.seat)
