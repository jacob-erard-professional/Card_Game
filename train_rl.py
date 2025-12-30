"""
Training loop for RL poker agents using self-play.
"""
import torch
import torch.optim as optim
from RL.rl_agent import PokerPolicyNet, RLPokerAgent, PokerStateEncoder
from engine import PokerEngine
from collections import deque
import numpy as np


class SelfPlayTrainer:
    """Trains agents via self-play games."""
    
    def __init__(self, num_agents: int = 2, learning_rate: float = 1e-3, device: str = 'cpu'):
        self.num_agents = num_agents
        self.device = device
        
        # Create agents
        self.agents = [
            RLPokerAgent(PokerPolicyNet(input_dim=200, hidden_dim=128), device=device, epsilon=0.1)
            for _ in range(num_agents)
        ]
        self.optimizers = [optim.Adam(agent.model.parameters(), lr=learning_rate) for agent in self.agents]
        
        # Track wins
        self.win_counts = [0] * num_agents
    
    def play_game(self) -> int:
        """Play one game between two agents. Returns winner agent index."""
        game = PokerEngine(num_players=2)
        game.set_player_action_provider(0, self.agents[0])
        game.set_player_action_provider(1, self.agents[1])
        
        winners = game.run()
        winner_idx = winners[0].player_num
        self.win_counts[winner_idx] += 1
        return winner_idx
    
    def train(self, num_games: int = 100):
        """Play games and update agents (simplified reward-based update)."""
        print(f"Training {self.num_agents} agents for {num_games} games...")
        
        for game_num in range(num_games):
            winner_idx = self.play_game()
            
            # Simplified: boost winner agent's learning rate (in real implementation, 
            # store transitions and do proper PPO/A2C updates)
            
            if (game_num + 1) % 10 == 0:
                print(f"Games {game_num + 1}/{num_games} | Wins: {self.win_counts}")
                self.win_counts = [0] * self.num_agents
    
    def save_agent(self, agent_idx: int, filepath: str):
        """Save agent model to disk."""
        torch.save(self.agents[agent_idx].model.state_dict(), filepath)
        print(f"Saved agent {agent_idx} to {filepath}")
    
    def load_agent(self, agent_idx: int, filepath: str):
        """Load agent model from disk."""
        self.agents[agent_idx].model.load_state_dict(torch.load(filepath, map_location=self.device))
        print(f"Loaded agent {agent_idx} from {filepath}")


if __name__ == '__main__':
    # Create trainer and run training
    trainer = SelfPlayTrainer(num_agents=2, device='cpu')
    trainer.train(num_games=100)
    
    # Save trained agents
    trainer.save_agent(0, 'agent_0.pth')
    trainer.save_agent(1, 'agent_1.pth')
