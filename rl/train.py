from __future__ import annotations

import argparse
import random
from dataclasses import dataclass

import numpy as np

from rl.dqn import DQN, ReplayBuffer, Transition, make_optimizer, select_action, torch, train_batch
from rl.encoding import observation_size
from rl.environment import PokerRLEnv


@dataclass
class EvalResult:
    episodes: int
    avg_reward: float
    win_rate: float


def evaluate(policy: DQN, episodes: int, num_players: int, max_players: int, blind_amount: int) -> EvalResult:
    wins = 0
    total_reward = 0.0
    env = PokerRLEnv(
        num_players=num_players,
        blind_amount=blind_amount,
        max_players=max_players,
        quiet=True,
    )

    for _ in range(episodes):
        state, mask = env.reset()
        done = env.engine.hand_over
        reward = (
            env.engine.chip_deltas().get(env.controlled_player, 0) / max(1, blind_amount)
            if done else 0.0
        )
        while not done:
            action = select_action(policy, state, mask, epsilon=0.0)
            result = env.step(action)
            state = result.observation
            mask = result.mask
            done = result.terminal
            reward = result.reward
        total_reward += reward
        wins += int(reward > 0)

    return EvalResult(
        episodes=episodes,
        avg_reward=total_reward / max(1, episodes),
        win_rate=wins / max(1, episodes),
    )


def train(
    episodes: int,
    output: str,
    num_players: int = 2,
    max_players: int = 6,
    batch_size: int = 64,
    target_sync: int = 250,
    eval_interval: int = 250,
    eval_episodes: int = 100,
    blind_amount: int = 20,
    seed: int | None = None,
) -> None:
    if torch is None:
        raise ImportError("PyTorch is required for training. Install torch first.")

    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)

    env = PokerRLEnv(
        num_players=num_players,
        blind_amount=blind_amount,
        max_players=max_players,
        quiet=True,
    )
    input_size = observation_size(max_players)
    policy = DQN(input_size)
    target = DQN(input_size)
    target.load_state_dict(policy.state_dict())
    optimizer = make_optimizer(policy)
    replay = ReplayBuffer(capacity=50000)

    steps = 0
    rewards_window: list[float] = []
    losses_window: list[float] = []
    action_counts = [0] * 5

    print(f"training episodes={episodes} output={output}")
    for episode in range(1, episodes + 1):
        state, mask = env.reset()
        done = env.engine.hand_over
        epsilon = max(0.05, 1.0 - episode / max(1, episodes * 0.75))
        final_reward = (
            env.engine.chip_deltas().get(env.controlled_player, 0) / max(1, blind_amount)
            if done else 0.0
        )

        while not done:
            action = select_action(policy, state, mask, epsilon)
            action_counts[action] += 1
            result = env.step(action)
            replay.push(Transition(
                state=state,
                action=action,
                reward=result.reward,
                next_state=result.observation,
                done=result.terminal,
                next_mask=result.mask,
            ))
            state = result.observation
            mask = result.mask
            done = result.terminal
            final_reward = result.reward
            steps += 1

            if len(replay) >= batch_size:
                loss = train_batch(policy, target, optimizer, replay.sample(batch_size))
                losses_window.append(loss)
                if len(losses_window) > 200:
                    losses_window.pop(0)

            if steps % target_sync == 0:
                target.load_state_dict(policy.state_dict())

        rewards_window.append(final_reward)
        if len(rewards_window) > 200:
            rewards_window.pop(0)

        if episode == 1 or episode % eval_interval == 0 or episode == episodes:
            avg_reward = sum(rewards_window) / max(1, len(rewards_window))
            avg_loss = sum(losses_window) / max(1, len(losses_window)) if losses_window else 0.0
            eval_result = evaluate(policy, eval_episodes, num_players, max_players, blind_amount)
            print(
                f"episode={episode:>6} steps={steps:>7} epsilon={epsilon:.3f} "
                f"train_avg_reward={avg_reward:+.3f} loss={avg_loss:.4f} "
                f"eval_avg_reward={eval_result.avg_reward:+.3f} "
                f"eval_win_rate={eval_result.win_rate:.1%} "
                f"actions={action_counts}"
            )

    torch.save(policy.state_dict(), output)
    print(f"saved {output}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=2000)
    parser.add_argument("--output", default="rl_model.pt")
    parser.add_argument("--players", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--target-sync", type=int, default=250)
    parser.add_argument("--eval-interval", type=int, default=250)
    parser.add_argument("--eval-episodes", type=int, default=100)
    parser.add_argument("--blind", type=int, default=20)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    train(
        episodes=args.episodes,
        output=args.output,
        num_players=args.players,
        batch_size=args.batch_size,
        target_sync=args.target_sync,
        eval_interval=args.eval_interval,
        eval_episodes=args.eval_episodes,
        blind_amount=args.blind,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
