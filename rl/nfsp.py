"""Neural Fictitious Self-Play (Heinrich & Silver, 2016).

Each agent learns two networks:
- a best-response Q-network, trained with double DQN on its own experience, and
- an average policy network, trained by supervised learning on the best-response actions.

In self-play each seat acts with the best response with probability `eta` and with the
average policy otherwise. The average policy is the one you deploy: it converges toward
an equilibrium and plays mixed strategies (it bluffs at a frequency, not always or never).

Acting happens on CPU copies of the networks; learning happens on `device`. Single-state
inference on Apple's MPS is ~150x slower than CPU, while large-batch training is faster.
"""
from __future__ import annotations

import copy
import random
from dataclasses import asdict, dataclass

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from rl.actions import ACTION_COUNT

BEST_RESPONSE = "best_response"
AVERAGE = "average"


def resolve_device(name: str = "auto") -> torch.device:
    if name != "auto":
        return torch.device(name)
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def mlp(input_size: int, hidden: int, output_size: int = ACTION_COUNT) -> nn.Module:
    return nn.Sequential(
        nn.Linear(input_size, hidden),
        nn.ReLU(),
        nn.Linear(hidden, hidden),
        nn.ReLU(),
        nn.Linear(hidden, output_size),
    )


@dataclass
class NFSPConfig:
    hidden: int = 512
    batch_size: int = 1024
    rl_capacity: int = 300_000
    sl_capacity: int = 1_000_000
    q_lr: float = 2e-4
    pi_lr: float = 1e-4
    eta: float = 0.1
    epsilon_start: float = 0.1
    epsilon_end: float = 0.005
    learn_every: int = 64
    target_sync: int = 500
    actor_sync: int = 20
    min_buffer: int = 5_000


class ReplayBuffer:
    """Circular buffer of (obs, action, reward, next_obs, next_mask, done) transitions."""

    def __init__(self, capacity: int, obs_size: int):
        self.capacity = capacity
        self.obs = np.zeros((capacity, obs_size), dtype=np.float16)
        self.next_obs = np.zeros((capacity, obs_size), dtype=np.float16)
        self.actions = np.zeros(capacity, dtype=np.int64)
        self.rewards = np.zeros(capacity, dtype=np.float32)
        self.next_masks = np.zeros((capacity, ACTION_COUNT), dtype=bool)
        self.dones = np.zeros(capacity, dtype=bool)
        self.size = 0
        self.cursor = 0

    def add(self, obs, action, reward, next_obs, next_mask, done) -> None:
        i = self.cursor
        self.obs[i] = obs
        self.actions[i] = action
        self.rewards[i] = reward
        self.dones[i] = done
        if not done:
            self.next_obs[i] = next_obs
            self.next_masks[i] = next_mask
        self.cursor = (i + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)

    def sample(self, batch_size: int, rng: np.random.Generator):
        idx = rng.integers(0, self.size, batch_size)
        return self.obs[idx], self.actions[idx], self.rewards[idx], self.next_obs[idx], self.next_masks[idx], self.dones[idx]


class ReservoirBuffer:
    """Uniform sample of every (obs, action, mask) ever added, so the average policy averages over all of training."""

    def __init__(self, capacity: int, obs_size: int):
        self.capacity = capacity
        self.obs = np.zeros((capacity, obs_size), dtype=np.float16)
        self.actions = np.zeros(capacity, dtype=np.int64)
        self.masks = np.zeros((capacity, ACTION_COUNT), dtype=bool)
        self.size = 0
        self.seen = 0

    def add(self, obs, action, mask, rng: random.Random) -> None:
        self.seen += 1
        if self.size < self.capacity:
            i = self.size
            self.size += 1
        else:
            i = rng.randrange(self.seen)
            if i >= self.capacity:
                return
        self.obs[i] = obs
        self.actions[i] = action
        self.masks[i] = mask

    def sample(self, batch_size: int, rng: np.random.Generator):
        idx = rng.integers(0, self.size, batch_size)
        return self.obs[idx], self.actions[idx], self.masks[idx]


def masked_logits(logits: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    return logits.masked_fill(~mask, -1e9)


class NFSPAgent:
    def __init__(self, obs_size: int, config: NFSPConfig, device: torch.device, seed: int | None = None):
        self.obs_size = obs_size
        self.config = config
        self.device = device
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)

        self.q = mlp(obs_size, config.hidden).to(device)
        self.q_target = copy.deepcopy(self.q)
        self.pi = mlp(obs_size, config.hidden).to(device)
        self.q_opt = torch.optim.Adam(self.q.parameters(), lr=config.q_lr)
        self.pi_opt = torch.optim.Adam(self.pi.parameters(), lr=config.pi_lr)
        self.q_actor = mlp(obs_size, config.hidden)
        self.pi_actor = mlp(obs_size, config.hidden)
        self._sync_actors()

        self.rl_buffer = ReplayBuffer(config.rl_capacity, obs_size)
        self.sl_buffer = ReservoirBuffer(config.sl_capacity, obs_size)
        self.learn_steps = 0
        self.transitions_since_learn = 0

    def act(self, obs: np.ndarray, mask: np.ndarray, mode: str, epsilon: float) -> int:
        legal = np.flatnonzero(mask)
        if mode == BEST_RESPONSE and self.rng.random() < epsilon:
            return int(self.rng.choice(legal))
        with torch.no_grad():
            x = torch.from_numpy(obs).unsqueeze(0)
            m = torch.from_numpy(mask).unsqueeze(0)
            if mode == BEST_RESPONSE:
                return int(masked_logits(self.q_actor(x), m).argmax())
            probs = F.softmax(masked_logits(self.pi_actor(x), m), dim=1)[0].numpy()
        return int(self.np_rng.choice(len(probs), p=probs / probs.sum()))

    def record_rl(self, obs, action, reward, next_obs, next_mask, done) -> None:
        self.rl_buffer.add(obs, action, reward, next_obs, next_mask, done)
        self.transitions_since_learn += 1
        if self.transitions_since_learn >= self.config.learn_every:
            self.transitions_since_learn = 0
            self.learn()

    def record_sl(self, obs, action, mask) -> None:
        self.sl_buffer.add(obs, action, mask, self.rng)

    def learn(self) -> dict[str, float]:
        cfg = self.config
        if self.rl_buffer.size < cfg.min_buffer or self.sl_buffer.size < cfg.min_buffer:
            return {}
        stats = {"q_loss": self._learn_q(), "pi_loss": self._learn_pi()}
        self.learn_steps += 1
        if self.learn_steps % cfg.target_sync == 0:
            self.q_target.load_state_dict(self.q.state_dict())
        if self.learn_steps % cfg.actor_sync == 0:
            self._sync_actors()
        self.last_stats = stats
        return stats

    def _tensor(self, array, dtype=None) -> torch.Tensor:
        tensor = torch.from_numpy(np.ascontiguousarray(array))
        if dtype is not None:
            tensor = tensor.to(dtype)
        return tensor.to(self.device, non_blocking=True)

    def _learn_q(self) -> float:
        obs, actions, rewards, next_obs, next_masks, dones = self.rl_buffer.sample(self.config.batch_size, self.np_rng)
        obs = self._tensor(obs, torch.float32)
        next_obs = self._tensor(next_obs, torch.float32)
        actions = self._tensor(actions)
        rewards = self._tensor(rewards)
        next_masks = self._tensor(next_masks)
        dones = self._tensor(dones)

        q_taken = self.q(obs).gather(1, actions.unsqueeze(1)).squeeze(1)
        with torch.no_grad():
            # Double DQN: the online net picks the next action, the target net scores it.
            next_best = masked_logits(self.q(next_obs), next_masks).argmax(dim=1, keepdim=True)
            next_value = self.q_target(next_obs).gather(1, next_best).squeeze(1)
            # Each hand is an episode with no discounting; terminal transitions have no next value.
            target = rewards + torch.where(dones, torch.zeros_like(next_value), next_value)

        loss = F.smooth_l1_loss(q_taken, target)
        self.q_opt.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.q.parameters(), 10.0)
        self.q_opt.step()
        return float(loss.item())

    def _learn_pi(self) -> float:
        obs, actions, masks = self.sl_buffer.sample(self.config.batch_size, self.np_rng)
        logits = masked_logits(self.pi(self._tensor(obs, torch.float32)), self._tensor(masks))
        loss = F.cross_entropy(logits, self._tensor(actions))
        self.pi_opt.zero_grad()
        loss.backward()
        self.pi_opt.step()
        return float(loss.item())

    def _sync_actors(self) -> None:
        self.q_actor.load_state_dict({k: v.detach().cpu() for k, v in self.q.state_dict().items()})
        self.pi_actor.load_state_dict({k: v.detach().cpu() for k, v in self.pi.state_dict().items()})

    def training_state(self) -> dict:
        return {
            "config": asdict(self.config),
            "obs_size": self.obs_size,
            "q": self.q.state_dict(),
            "q_target": self.q_target.state_dict(),
            "pi": self.pi.state_dict(),
            "q_opt": self.q_opt.state_dict(),
            "pi_opt": self.pi_opt.state_dict(),
            "learn_steps": self.learn_steps,
        }

    def load_training_state(self, state: dict) -> None:
        self.q.load_state_dict(state["q"])
        self.q_target.load_state_dict(state["q_target"])
        self.pi.load_state_dict(state["pi"])
        self.q_opt.load_state_dict(state["q_opt"])
        self.pi_opt.load_state_dict(state["pi_opt"])
        self.learn_steps = state["learn_steps"]
        self._sync_actors()
