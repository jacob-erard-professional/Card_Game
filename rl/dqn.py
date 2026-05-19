from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

from rl.actions import ACTION_COUNT


try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
except ImportError:  # pragma: no cover - exercised when torch is not installed
    torch = None
    nn = None
    optim = None


class DQN(nn.Module if nn is not None else object):
    def __init__(self, input_size: int, output_size: int = ACTION_COUNT):
        if nn is None:
            raise ImportError("PyTorch is required for DQN. Install torch first.")
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_size, 128),
            nn.ReLU(),
            nn.Linear(128, 128),
            nn.ReLU(),
            nn.Linear(128, output_size),
        )

    def forward(self, x):
        return self.net(x)


@dataclass
class Transition:
    state: list[float]
    action: int
    reward: float
    next_state: list[float]
    done: bool
    next_mask: list[bool]


class ReplayBuffer:
    def __init__(self, capacity: int = 10000):
        self.items = deque(maxlen=capacity)

    def push(self, transition: Transition) -> None:
        self.items.append(transition)

    def sample(self, batch_size: int) -> list[Transition]:
        return random.sample(self.items, batch_size)

    def __len__(self) -> int:
        return len(self.items)


def select_action(model: DQN, state: list[float], mask: list[bool], epsilon: float = 0.0) -> int:
    legal_indices = [idx for idx, allowed in enumerate(mask) if allowed]
    if not legal_indices:
        raise RuntimeError("No legal actions available")
    if random.random() < epsilon:
        return random.choice(legal_indices)

    with torch.no_grad():
        q_values = model(torch.tensor([state], dtype=torch.float32))[0]
        illegal_value = torch.tensor(-1e9, dtype=torch.float32)
        masked = torch.stack([
            q_values[idx] if allowed else illegal_value
            for idx, allowed in enumerate(mask)
        ])
        return int(torch.argmax(masked).item())


def train_batch(policy: DQN, target: DQN, optimizer, batch: list[Transition], gamma: float = 0.99) -> float:
    states = torch.tensor([t.state for t in batch], dtype=torch.float32)
    actions = torch.tensor([t.action for t in batch], dtype=torch.int64).unsqueeze(1)
    rewards = torch.tensor([t.reward for t in batch], dtype=torch.float32)
    next_states = torch.tensor([t.next_state for t in batch], dtype=torch.float32)
    dones = torch.tensor([t.done for t in batch], dtype=torch.bool)

    q_values = policy(states).gather(1, actions).squeeze(1)
    with torch.no_grad():
        next_q = target(next_states)
        for row, transition in enumerate(batch):
            for idx, allowed in enumerate(transition.next_mask):
                if not allowed:
                    next_q[row, idx] = -1e9
        next_values = next_q.max(dim=1).values
        next_values[dones] = 0.0
        expected = rewards + gamma * next_values

    loss = nn.functional.smooth_l1_loss(q_values, expected)
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()
    return float(loss.item())


def make_optimizer(model: DQN, lr: float = 1e-3):
    if optim is None:
        raise ImportError("PyTorch is required for DQN training. Install torch first.")
    return optim.Adam(model.parameters(), lr=lr)
