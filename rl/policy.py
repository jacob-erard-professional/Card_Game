from __future__ import annotations

from rl.actions import ACTION_COUNT, action_from_index
from rl.dqn import DQN, select_action, torch
from rl.encoding import observation_size, observation_vector


def load_policy(model_path: str, input_size: int) -> DQN:
    if torch is None:
        raise ImportError("PyTorch is required to load an RL policy. Install torch first.")
    model = DQN(input_size=input_size, output_size=ACTION_COUNT)
    state = torch.load(model_path, map_location="cpu")
    model.load_state_dict(state)
    model.eval()
    return model


def make_rl_action_provider(model_path: str, deterministic: bool = True, max_players: int = 6):
    """Create a PokerEngine-compatible provider backed by a trained DQN."""
    model = load_policy(model_path, observation_size(max_players))

    def provider(game, player) -> str:
        engine = getattr(game, "_engine", None)
        if engine is None:
            raise RuntimeError("RL provider requires PokerEngine to attach itself to PokerState")
        state = observation_vector(engine, player.player_num, max_players)
        mask = engine.legal_action_mask(player.player_num)
        action_idx = select_action(model, state, mask, epsilon=0.0 if deterministic else 0.05)
        return action_from_index(engine, action_idx)

    return provider
