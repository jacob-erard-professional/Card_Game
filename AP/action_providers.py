from models.player import Player
from models.game import PokerState
import random
from actions.action import ActionType

def call_AP(game: PokerState, player: Player) -> str:
    return 'call'

def fold_AP(game:PokerState, player:Player)-> str:
    return 'fold'

def allin_AP(game:PokerState, player:Player)-> str:
    return 'allin'

def random_choice_AP(game:PokerState, player:Player)-> str:
    engine = getattr(game, "_engine", None)
    if engine is not None:
        legal = engine.legal_actions(player.player_num)
        if legal:
            checks_or_calls = [a for a in legal if a.action_type in (ActionType.CHECK, ActionType.CALL)]
            raises = [a for a in legal if a.action_type == ActionType.RAISE]
            weighted = []
            weighted.extend(checks_or_calls * 5)
            weighted.extend(raises * 3)
            weighted.extend([a for a in legal if a.action_type == ActionType.ALL_IN])
            weighted.extend([a for a in legal if a.action_type == ActionType.FOLD])
            return random.choice(weighted or legal)
    
    current_bet = max((p.bet for p in game.players), default=0)
    amount_to_call = current_bet - player.bet

    if amount_to_call > 0:
        choice = random.choices(['call', 'raise'], weights=[0.5, 0.5])[0]
        if choice == 'call' or choice == 'allin':
            return choice

        max_raise = max(0, player.chips.total() - amount_to_call)
        if max_raise <= 0:
            return 'call'
        raise_amt = random.randint(1, max(1, max_raise))
        return f'raise {raise_amt}'

    # No outstanding bet: allow check, raise, or fold with probabilities
    choice = random.choices(['check', 'raise', 'fold'], weights=[0.475, 0.475, 0.05])[0]
    if choice != 'raise':
        return choice

    # raise when no call required: pick a small bet fraction of chips
    max_raise = player.chips.total()
    if max_raise <= 0:
        return 'check'
    
    raise_amt = max(1, int(max_raise * random.uniform(0.05, 0.25)))
    return f'raise {raise_amt}'
