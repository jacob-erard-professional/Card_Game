from models.game import PokerState
from models.player import Player
from typing import Callable, Dict, Optional


class BettingManager:
    """
    Manages all betting-related functionality including:
    - Posting blinds
    - Processing player betting actions (fold, check, call, raise, all-in)
    - Executing complete betting rounds
    """
    
    def __init__(self, game: PokerState, action_providers: Optional[Dict[int, Callable[[PokerState, Player], str]]] = None):
        """
        Initialize the BettingManager.
        
        Args:
            game: The PokerState game object
            action_providers: Optional dict mapping player numbers to action provider functions
        """
        self.game = game
        self.action_providers = action_providers
    
    def preflop_betting_round(self):
        """Execute the preflop betting round with blinds."""
        self._post_blinds()
        
        num_players = len(self.game.players)
        big_blind_idx = (self.game.dealer_index + 2) % num_players
        first_to_act = (big_blind_idx + 1) % num_players
        
        self._betting_round(first_to_act)
    
    def postflop_betting_round(self):
        """Execute a postflop betting round (flop, turn, or river)."""
        # Reset bets for new round
        for p in self.game.players:
            p.bet = 0
        
        # First to act is left of dealer
        first_to_act = (self.game.dealer_index + 1) % len(self.game.players)
        self._betting_round(first_to_act)
    
    # ========== Private/Internal Methods ==========
    
    def _post_amount(self, player: Player, amount: int):
        """Transfer chips from player to pot, handling insufficient funds."""
        available = player.chips.total()
        actual_amount = min(amount, available)
        
        if actual_amount > 0:
            try:
                player.chips.transfer_to(self.game.pot, actual_amount)
                player.bet += actual_amount
            except Exception as e:
                print(f"Error transferring chips: {e}")
    
    def _post_blinds(self):
        """Post small and big blinds."""
        num_players = len(self.game.players)
        small_idx = (self.game.dealer_index + 1) % num_players
        big_idx = (self.game.dealer_index + 2) % num_players
        
        # Reset all bets
        for p in self.game.players:
            p.bet = 0
        
        # Post blinds
        self._post_amount(self.game.players[small_idx], self.game.blind_amount)
        self._post_amount(self.game.players[big_idx], self.game.blind_amount * 2)
    
    def _get_current_bet(self) -> int:
        """Get the current bet that players need to match."""
        return max((p.bet for p in self.game.players), default=0)
    
    def _get_active_players(self) -> list[Player]:
        """Get players who haven't folded."""
        return [p for p in self.game.players if not p.folded]
    
    def _can_player_act(self, player: Player, current_bet: int) -> bool:
        """Check if a player can take an action."""
        return (not player.folded and 
                player.chips.total() > 0 and 
                player.bet != current_bet)
    
    def _print_action_header(self, player_idx: int, current_bet: int):
        """Print betting round status for console play."""
        print(f"\n--- Player {player_idx} Action ---")
        print(f"Pot: {self.game.pot.total()} | Current bet to match: {current_bet}")
    
    def _print_round_summary(self):
        """Print summary at end of betting round."""
        print("\n--- Betting Round Complete ---")
        for p in self.game.players:
            status = "folded" if p.folded else f"in (bet: {p.bet}, remaining: {p.chips.total()})"
            print(f"Player {p.player_num}: {status}")
        print(f"Final Pot: {self.game.pot.total()}\n")
    
    def _process_fold(self, player: Player, player_idx: int, is_console: bool) -> bool:
        """Process a fold action. Returns True if action is valid."""
        player.folded = True
        if is_console:
            print(f"Player {player_idx} folded\n")
        return True
    
    def _process_check(self, player: Player, player_idx: int, current_bet: int, is_console: bool) -> bool:
        """Process a check action. Returns True if action is valid."""
        if player.bet != current_bet:
            if is_console:
                print(f"Invalid: cannot check when {current_bet - player.bet} chips are owed. Try 'call' or 'raise'.\n")
            return False
        
        if is_console:
            print(f"Player {player_idx} checked\n")
        return True
    
    def _process_call(self, player: Player, player_idx: int, current_bet: int, is_console: bool) -> bool:
        """Process a call action. Returns True (always valid)."""
        amount_to_call = current_bet - player.bet
        if amount_to_call > 0:
            self._post_amount(player, amount_to_call)
            if is_console:
                print(f"Player {player_idx} called {amount_to_call}")
                print(f"Pot: {self.game.pot.total()}\n")
        else:
            if is_console:
                print(f"Player {player_idx} checked (nothing to call)\n")
        return True
    
    def _process_allin(self, player: Player, player_idx: int, current_bet: int, is_console: bool) -> tuple[bool, int, Optional[int]]:
        """
        Process an all-in action. 
        Returns (is_valid, new_current_bet, last_raiser_idx or None)
        """
        amt = player.chips.total()
        self._post_amount(player, amt)
        
        new_current_bet = current_bet
        last_raiser = None
        
        if player.bet > current_bet:
            new_current_bet = player.bet
            last_raiser = player_idx
        
        if is_console:
            print(f"Player {player_idx} went all-in for {amt}")
            print(f"Pot: {self.game.pot.total()}\n")
        
        return True, new_current_bet, last_raiser
    
    def _process_raise(self, action: str, player: Player, player_idx: int, 
                      current_bet: int, is_console: bool) -> tuple[bool, int, Optional[int]]:
        """
        Process a raise action.
        Returns (is_valid, new_current_bet, last_raiser_idx or None)
        """
        parts = action.split()
        if len(parts) >= 2:
            try:
                raise_amt = int(parts[1])
            except ValueError:
                raise_amt = None
        else:
            raise_amt = None
        
        if raise_amt is None or raise_amt <= 0:
            if is_console:
                print(f"Invalid raise: must specify positive amount. Usage: 'raise <amount>'\n")
            return False, current_bet, None
        
        amount_to_call = current_bet - player.bet
        total_required = amount_to_call + raise_amt
        self._post_amount(player, total_required)
        
        new_current_bet = current_bet
        last_raiser = None
        
        if player.bet > current_bet:
            new_current_bet = player.bet
            last_raiser = player_idx
        
        if is_console:
            print(f"Player {player_idx} raised by {raise_amt} (total: {total_required})")
            print(f"Pot: {self.game.pot.total()}\n")
        
        return True, new_current_bet, last_raiser
    
    def _handle_player_action(self, player_idx: int, current_bet: int, 
                             providers: Dict, is_console: bool) -> tuple[int, Optional[int]]:
        """
        Handle a single player's action.
        Returns (new_current_bet, last_raiser_idx or None)
        """
        player = self.game.players[player_idx]
        provider = providers.get(player.player_num)
        
        if is_console:
            self._print_action_header(player_idx, current_bet)
        
        # Keep prompting until valid action
        action_valid = False
        new_current_bet = current_bet
        last_raiser = None
        
        while not action_valid:
            action = provider(self.game, player).lower()
            
            if action.startswith('fold'):
                action_valid = self._process_fold(player, player_idx, is_console)
            
            elif action.startswith('check'):
                action_valid = self._process_check(player, player_idx, current_bet, is_console)
            
            elif action.startswith('call'):
                action_valid = self._process_call(player, player_idx, current_bet, is_console)
            
            elif action.startswith('allin'):
                action_valid, new_current_bet, last_raiser = self._process_allin(
                    player, player_idx, current_bet, is_console)
            
            elif action.startswith('raise'):
                action_valid, new_current_bet, last_raiser = self._process_raise(
                    action, player, player_idx, current_bet, is_console)
            
            else:
                if is_console:
                    print(f"Invalid action. Valid actions: fold, check, call, raise <amount>, allin\n")
        
        return new_current_bet, last_raiser
    
    def _betting_round(self, starting_player_idx: int):
        """
        Execute a complete betting round starting from the specified player.
        """
        providers = self._get_providers()
        is_console = self.action_providers is None
        num_players = len(self.game.players)
        
        current_bet = self._get_current_bet()
        
        # Check if betting can even occur
        active_with_chips = [p for p in self.game.players 
                            if not p.folded and p.chips.total() > 0]
        if len(active_with_chips) <= 1:
            if is_console:
                self._print_round_summary()
            return
        
        # Track who has acted this round
        has_acted = {i: False for i in range(num_players)}
        last_raiser_idx = None
        
        idx = starting_player_idx
        
        while True:
            player = self.game.players[idx]
            
            # Skip folded or all-in players
            if player.folded or player.chips.total() == 0:
                idx = (idx + 1) % num_players
                
                # Check termination: everyone has either acted and matched the bet, folded, or is all-in
                all_done = all(
                    p.folded or 
                    p.chips.total() == 0 or 
                    (has_acted[i] and p.bet == current_bet)
                    for i, p in enumerate(self.game.players)
                )
                if all_done:
                    break
                continue
            
            # Skip if player has already acted and matched current bet (unless there was a raise after them)
            if has_acted[idx] and player.bet == current_bet and (last_raiser_idx is None or idx != last_raiser_idx):
                idx = (idx + 1) % num_players
                
                # Check termination
                all_done = all(
                    p.folded or 
                    p.chips.total() == 0 or 
                    (has_acted[i] and p.bet == current_bet)
                    for i, p in enumerate(self.game.players)
                )
                if all_done:
                    break
                continue
            
            # Handle player action
            new_bet, raiser_idx = self._handle_player_action(
                idx, current_bet, providers, is_console)
            
            has_acted[idx] = True
            
            if raiser_idx is not None:
                last_raiser_idx = raiser_idx
                current_bet = new_bet
            
            # Check for immediate end: only one non-folded player
            if len(self._get_active_players()) <= 1:
                break
            
            # Check termination: everyone has acted and matched the bet (or folded/all-in)
            all_done = all(
                p.folded or 
                p.chips.total() == 0 or 
                (has_acted[i] and p.bet == current_bet)
                for i, p in enumerate(self.game.players)
            )
            if all_done:
                break
            
            idx = (idx + 1) % num_players
        
        if is_console:
            self._print_round_summary()
    
    def _get_providers(self) -> Dict[int, Callable[[PokerState, Player], str]]:
        """Get action providers, defaulting to console if not set."""
        # If no providers mapping was supplied, use console for all players
        if self.action_providers is None:
            provider = self._get_console_provider()
            return {p.player_num: provider for p in self.game.players}

        # If a partial mapping was supplied, ensure every player has a provider
        providers: Dict[int, Callable[[PokerState, Player], str]] = dict(self.action_providers)
        console_provider = self._get_console_provider()
        for p in self.game.players:
            if providers.get(p.player_num) is None:
                providers[p.player_num] = console_provider
        return providers
    
    def _get_console_provider(self) -> Callable[[PokerState, Player], str]:
        """Returns a console input provider for local play."""
        def console_provider(g: PokerState, p: Player) -> str:
            prompt = (f"Player {p.player_num} "
                     f"(chips={p.chips.total()}, bet={p.bet}) "
                     f"action [fold/check/call/raise <amt>/allin]: ")
            return input(prompt).strip()
        return console_provider
