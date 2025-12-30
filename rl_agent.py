import torch
import torch.nn as nn
import torch.nn.functional as F
from models.game import PokerState
from models.player import Player
from typing import Tuple, List
import numpy as np


class PokerStateEncoder:
    """Converts PokerState to feature vector for the neural network."""
    
    RANK_MAP = {2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5, 8: 6, 9: 7, 10: 8, 11: 9, 12: 10, 13: 11, 14: 12}
    SUIT_MAP = {'H': 0, 'D': 1, 'C': 2, 'S': 3}
    
    @staticmethod
    def encode_card(card) -> List[float]:
        """Encode a single card as [rank_one_hot (13), suit_one_hot (4)]."""
        rank_vec = [0] * 13
        rank_vec[PokerStateEncoder.RANK_MAP[card.rank.value]] = 1
        suit_vec = [0] * 4
        suit_vec[PokerStateEncoder.SUIT_MAP[card.suit.value]] = 1
        return rank_vec + suit_vec
    
    @staticmethod
    def encode(game: PokerState, player: Player) -> np.ndarray:
        """
        Encode game state for the player.
        
        Features:
        - Player's hole cards (2 cards × 17 features)
        - Community cards (5 cards × 17 features, padded with zeros)
        - Current bet (1)
        - Player chips (1)
        - Pot size (1)
        - Position (1, one-hot encoded per player count)
        - Active players count (1)
        - Opponent chips (normalized, variable)
        
        Returns: np.ndarray of shape (feature_dim,)
        """
        features = []
        
        # Encode hole cards
        for card in player.hand:
            features.extend(PokerStateEncoder.encode_card(card))
        
        # Pad if fewer than 2 hole cards
        while len(player.hand) < 2:
            features.extend([0] * 17)
        
        # Encode community cards (up to 5)
        for card in game.community_cards:
            features.extend(PokerStateEncoder.encode_card(card))
        while len(game.community_cards) < 5:
            features.extend([0] * 17)
        
        # Game state scalars (normalized)
        max_chips = 10000  # Normalization constant
        features.append(min(player.bet / max_chips, 1.0))  # Current bet
        features.append(min(player.chips.total() / max_chips, 1.0))  # Player chips
        features.append(min(game.pot.total() / max_chips, 1.0))  # Pot size
        
        # Position (one-hot for up to 10 players)
        position_vec = [0] * 10
        position_vec[min(player.player_num, 9)] = 1
        features.extend(position_vec)
        
        # Count of active players (unfold the count)
        active_count = len(game.active_players())
        features.append(min(active_count / 10, 1.0))
        
        # Opponent chip counts (up to 9 opponents, normalized)
        opponent_chips = [p.chips.total() for p in game.players if p.player_num != player.player_num]
        for _ in range(9):
            if opponent_chips:
                features.append(min(opponent_chips.pop(0) / max_chips, 1.0))
            else:
                features.append(0.0)
        
        return np.array(features, dtype=np.float32)


class PokerPolicyNet(nn.Module):
    """Simple policy network for poker action selection."""
    
    def __init__(self, input_dim: int = 200, hidden_dim: int = 128):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, hidden_dim)
        self.policy_head = nn.Linear(hidden_dim, 4)  # 4 actions: fold, check/call, raise, allin
        self.value_head = nn.Linear(hidden_dim, 1)  # Value estimate for advantage
    
    def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            state: (batch_size, input_dim)
        
        Returns:
            action_logits: (batch_size, 4)
            value: (batch_size, 1)
        """
        x = F.relu(self.fc1(state))
        x = F.relu(self.fc2(x))
        action_logits = self.policy_head(x)
        value = self.value_head(x)
        return action_logits, value


class RLPokerAgent:
    """RL-based poker agent that can be used as an action provider."""
    
    ACTION_MAP = {
        0: 'fold',
        1: 'call',
        2: 'raise 50',  # Fixed raise amount for simplicity; could be parametrized
        3: 'allin',
    }
    
    def __init__(self, model: PokerPolicyNet, device: str = 'cpu', epsilon: float = 0.1):
        """
        Args:
            model: PokerPolicyNet instance
            device: 'cpu' or 'cuda'
            epsilon: Exploration rate (0 = greedy, 1 = random)
        """
        self.model = model.to(device)
        self.device = device
        self.epsilon = epsilon
    
    def __call__(self, game: PokerState, player: Player) -> str:
        """Action provider interface: (game, player) -> action string."""
        # Encode state
        state_np = PokerStateEncoder.encode(game, player)
        state_tensor = torch.from_numpy(state_np).unsqueeze(0).to(self.device)  # (1, feature_dim)
        
        # Forward pass
        with torch.no_grad():
            action_logits, _ = self.model(state_tensor)
        
        # Epsilon-greedy action selection
        if np.random.random() < self.epsilon:
            action_idx = np.random.randint(4)
        else:
            action_idx = action_logits.argmax(dim=1).item()
        
        return self.ACTION_MAP[action_idx]


# Example usage:
if __name__ == '__main__':
    from engine import PokerEngine
    
    # Create model and agent
    policy_net = PokerPolicyNet(input_dim=200, hidden_dim=128)
    agent = RLPokerAgent(policy_net, epsilon=0.1)
    
    # Test in a game
    game = PokerEngine(num_players=2)
    game.set_player_action_provider(0, agent)
    game.set_global_action_provider(agent)  # Both players use the same agent for now
    
    winner = game.run()
    print(f"Winner: Player {winner[0].player_num}")
