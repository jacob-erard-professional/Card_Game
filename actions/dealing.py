from models.game import PokerState
'''
Handles the four actions made by the dealer and updates
the state of the game.
'''
def deal(game: PokerState):
    for _ in range(2):
        for player in game.players:
            player.hand.append(game.deck.draw())
    game.phase = 'preflop'
            
def flop(game: PokerState):
    game.burn_cards.append(game.deck.draw())
    for _ in range(3):
        game.community_cards.append(game.deck.draw())
    game.state = 'flop'

def turn(game: PokerState):
    game.burn_cards.append(game.deck.draw())
    game.community_cards.append(game.deck.draw())
    game.state='turn'

def river(game: PokerState):
    game.burn_cards.append(game.deck.draw())
    game.community_cards.append(game.deck.draw())
    game.state='river'
