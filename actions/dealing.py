from models.game import PokerState


def deal_hole_cards(game: PokerState) -> None:
    for _ in range(2):
        for player in game.players:
            if player.sitting_out:
                continue
            player.hand.append(game.deck.draw())


def deal_board(game: PokerState, count: int) -> None:
    """Burn one card, then deal `count` community cards."""
    game.burn_cards.append(game.deck.draw())
    for _ in range(count):
        game.community_cards.append(game.deck.draw())
