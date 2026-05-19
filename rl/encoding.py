from __future__ import annotations

from models.card import Card


PHASES = ["preflop", "flop", "turn", "river"]


def card_features(card: Card | None) -> list[float]:
    if card is None:
        return [0.0, 0.0]
    return [card.rank.value / 14.0, list(type(card.suit)).index(card.suit) / 3.0]


def observation_vector(engine, player_num: int, max_players: int = 6) -> list[float]:
    game = engine.game
    blind = max(1, game.blind_amount)
    player = game.players[player_num]

    values: list[float] = []
    values.extend([1.0 if game.phase == phase else 0.0 for phase in PHASES])
    values.extend([
        game.pot.total() / blind,
        engine.current_bet / blind,
        engine.min_raise / blind,
        float(engine.current_actor == player_num),
        player.chips.total() / blind,
        player.bet / blind,
        player.committed / blind,
        float(player.folded),
        float(player.all_in),
    ])

    for idx in range(max_players):
        if idx < len(game.players):
            p = game.players[idx]
            values.extend([
                p.chips.total() / blind,
                p.bet / blind,
                p.committed / blind,
                float(p.folded),
                float(p.all_in),
            ])
        else:
            values.extend([0.0, 0.0, 0.0, 1.0, 0.0])

    cards = list(player.hand[:2])
    while len(cards) < 2:
        cards.append(None)
    community = list(game.community_cards[:5])
    while len(community) < 5:
        community.append(None)

    for card in cards + community:
        values.extend(card_features(card))

    return values


def observation_size(max_players: int = 6) -> int:
    return len([0.0] * (4 + 9 + max_players * 5 + 7 * 2))
