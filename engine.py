from models.card import Suit, Rank, Card, Deck
from models.chip import ChipHolder, Chip
from models.game import PokerState
from models.player import Player
from typing import Callable, Dict, Optional
import actions.dealing as dealing
from actions.showdown import showdown, award_pot


def initialize_game(num_players, blind_amount, chip_breakdown, denominations) -> PokerState:
    """
    Initialize a new poker game with players and chips.
    
    args:
        num_players: int -> Initial number of player
        blind_amount: int -> Amount to pay for blind
        chip_breakdown: dict -> Map of chips amount to number of chips initially for each player
        
    """
    
    # Create players
    players = []
    for i in range(num_players):
        player = Player(player_num=i, chips=ChipHolder(chip_breakdown))
        players.append(player)
    
    # Create the game state
    game = PokerState(
        blind_amount=blind_amount,
        players=players,
        community_cards=[],
        burn_cards = [],
        pot=ChipHolder(),
        dealer_index=0,
        current_player=1,
        deck=Deck(),
        phase="preflop"
    )
    
    return game

def initial_betting_round(
    game: PokerState,
    action_providers: Optional[Dict[int, Callable[[PokerState, Player], str]]] = None,
    ):
    """
    Run the initial (preflop) betting round.

    action_providers: optional mapping from player_num -> callable(game, player) -> action string.
    If not provided, uses console input for local play. Actions supported:
      - 'fold'
      - 'check'
      - 'call'
      - 'raise <amount>'  (amount is integer extra on top of call)
      - 'allin'

    The function is written so action collection can be swapped out for networked
    providers that return the same action strings.
    """
    is_console = action_providers is None
    
    if action_providers is None:
        def console_provider(g: PokerState, p: Player) -> str:
            prompt = f"Player {p.player_num} (chips={p.chips.total()}, bet={p.bet}) action [fold/check/call/raise <amt>/allin]: "
            return input(prompt).strip()

        action_providers = {p.player_num: console_provider for p in game.players}

    num_players = len(game.players)

    # Reset bets for the round
    for p in game.players:
        p.bet = 0

    # Post blinds (small and big)
    small_idx = (game.dealer_index + 1) % num_players
    big_idx = (game.dealer_index + 2) % num_players

    def post_amount(player: Player, amount: int):
        try:
            player.chips.transfer_to(game.pot, amount)
            player.bet += amount
        except Exception:
            # Player doesn't have enough for full amount -> push all they have
            remaining = player.chips.total()
            if remaining > 0:
                player.chips.transfer_to(game.pot, remaining)
                player.bet += remaining

    post_amount(game.players[small_idx], game.blind_amount)
    post_amount(game.players[big_idx], game.blind_amount * 2)

    if is_console:
        print(f"\n--- Blinds Posted ---")
        print(f"Small blind (Player {small_idx}): {game.players[small_idx].bet}")
        print(f"Big blind (Player {big_idx}): {game.players[big_idx].bet}")
        print(f"Pot: {game.pot.total()}\n")

    current_bet = max(p.bet for p in game.players)

    # First to act is player after big blind
    first_to_act = (big_idx + 1) % num_players

    # Track last raiser to know when cycle completes
    last_raiser = None

    # Helper to determine active players count
    def active_players():
        return [p for p in game.players if not p.folded and (p.chips.total() > 0 or p.bet > 0)]

    # If only one active player, betting ends
    if len([p for p in game.players if not p.folded]) <= 1:
        return

    idx = first_to_act
    # Continue until all non-folded players have either matched current_bet or are all-in
    while True:
        player = game.players[idx]

        # Skip folded or fully all-in players
        if player.folded or player.chips.total() == 0:
            idx = (idx + 1) % num_players
            # check termination
            if all((p.folded or p.chips.total() == 0 or p.bet == current_bet) for p in game.players if not p.folded):
                break
            if idx == first_to_act and last_raiser is None:
                break
            continue

        # If player already matched current bet, they may check
        provider = action_providers.get(player.player_num)
        
        if is_console:
            print(f"--- Player {idx} Action ---")
            print(f"Pot: {game.pot.total()} | Current bet to match: {current_bet}")

        # Keep prompting until valid action
        action_valid = False
        while not action_valid:
            action = provider(game, player).lower()

            if action.startswith('fold'):
                player.folded = True
                if is_console:
                    print(f"Player {idx} folded\n")
                action_valid = True
            elif action.startswith('check'):
                if player.bet != current_bet:
                    # Can't check if you owe money
                    if is_console:
                        print(f"Invalid: cannot check when {current_bet - player.bet} chips are owed. Try 'call' or 'raise'.\n")
                else:
                    if is_console:
                        print(f"Player {idx} checked\n")
                    action_valid = True
            elif action.startswith('call'):
                amount_to_call = current_bet - player.bet
                if amount_to_call > 0:
                    post_amount(player, amount_to_call)
                    if is_console:
                        print(f"Player {idx} called {amount_to_call}")
                        print(f"Pot: {game.pot.total()}\n")
                else:
                    if is_console:
                        print(f"Player {idx} checked (call with no amount to match)\n")
                action_valid = True
            elif action.startswith('allin'):
                amt = player.chips.total()
                post_amount(player, amt)
                if player.bet > current_bet:
                    current_bet = player.bet
                    last_raiser = idx
                if is_console:
                    print(f"Player {idx} went all-in for {amt}")
                    print(f"Pot: {game.pot.total()}\n")
                action_valid = True
            elif action.startswith('raise'):
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
                else:
                    amount_to_call = current_bet - player.bet
                    total_required = amount_to_call + raise_amt
                    post_amount(player, total_required)
                    if player.bet > current_bet:
                        current_bet = player.bet
                        last_raiser = idx
                    if is_console:
                        print(f"Player {idx} raised {total_required}")
                        print(f"Pot: {game.pot.total()}\n")
                    action_valid = True
            else:
                # Unrecognized action
                if is_console:
                    print(f"Invalid action. Valid actions: fold, check, call, raise <amount>, allin\n")

        # Check for immediate end: only one non-folded player
        if len([p for p in game.players if not p.folded]) == 1:
            break

        # Termination condition: all non-folded players have either matched current_bet or are all-in
        if all((p.folded or p.bet == current_bet or p.chips.total() == 0) for p in game.players):
            break

        idx = (idx + 1) % num_players

    # Betting round complete
    if is_console:
        print("--- Betting Round Complete ---")
        for p in game.players:
            status = "folded" if p.folded else f"in (bet: {p.bet}, remaining: {p.chips.total()})"
            print(f"Player {p.player_num}: {status}")
        print(f"Final Pot: {game.pot.total()}\n")


def blind(game: PokerState):
    # Post small blind only for compatibility if called directly
    try:
        game.players[(game.dealer_index + 1) % len(game.players)].chips.transfer_to(game.pot, game.blind_amount)
        game.players[(game.dealer_index + 1) % len(game.players)].bet += game.blind_amount
    except Exception:
        remaining = game.players[(game.dealer_index + 1) % len(game.players)].chips.total()
        if remaining > 0:
            game.players[(game.dealer_index + 1) % len(game.players)].chips.transfer_to(game.pot, remaining)
            game.players[(game.dealer_index + 1) % len(game.players)].bet += remaining
    
