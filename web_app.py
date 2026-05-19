from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory

from actions.action import Action, ActionType, parse_action
from engine import PokerEngine
from rl.actions import action_from_index
from rl.dqn import DQN, select_action, torch
from rl.encoding import observation_size, observation_vector


app = Flask(__name__, static_folder="web/static", static_url_path="/static")

MODEL_PATH = Path("rl_model.pt")
HUMAN_PLAYER = 0
RL_PLAYER = 1

engine: PokerEngine | None = None
model: DQN | None = None


def load_model() -> DQN | None:
    if torch is None or not MODEL_PATH.exists():
        return None
    loaded = DQN(observation_size())
    loaded.load_state_dict(torch.load(MODEL_PATH, map_location="cpu"))
    loaded.eval()
    return loaded


def new_engine() -> PokerEngine:
    game = PokerEngine(num_players=2, blind_amount=20, chip_breakdown={5: 100, 25: 20})
    game.game.players[HUMAN_PLAYER].name = "You"
    game.game.players[RL_PLAYER].name = "RL Model"
    game.start_hand()
    return game


def ensure_game() -> PokerEngine:
    global engine, model
    if model is None:
        model = load_model()
    if engine is None or len(engine.game.players) < 2:
        engine = new_engine()
        autoplay_rl()
    return engine


def rl_action(game: PokerEngine) -> Action:
    if model is not None:
        state = observation_vector(game, RL_PLAYER)
        mask = game.legal_action_mask(RL_PLAYER)
        action_index = select_action(model, state, mask, epsilon=0.0)
        return action_from_index(game, action_index)

    legal = game.legal_actions(RL_PLAYER)
    for preferred in (ActionType.CHECK, ActionType.CALL, ActionType.RAISE, ActionType.ALL_IN, ActionType.FOLD):
        for action in legal:
            if action.action_type == preferred:
                return action
    raise RuntimeError("RL opponent has no legal action")


def autoplay_rl() -> None:
    game = engine
    guard = 0
    while game is not None and not game.hand_over and game.current_actor == RL_PLAYER:
        guard += 1
        if guard > 100:
            raise RuntimeError("RL autoplay did not terminate")
        game.step(rl_action(game))


def card_payload(card) -> dict[str, str | int]:
    rank_map = {11: "J", 12: "Q", 13: "K", 14: "A"}
    suit_map = {"H": "hearts", "D": "diamonds", "C": "clubs", "S": "spades"}
    value = card.rank.value
    return {
        "rank": rank_map.get(value, str(value)),
        "suit": suit_map.get(card.suit.value, card.suit.value),
        "value": value,
    }


def action_payload(action: Action) -> dict[str, Any]:
    return {"type": action.action_type.value, "amount": action.amount}


def raise_bounds() -> dict[str, int | None]:
    game = ensure_game()
    if game.hand_over or game.current_actor != HUMAN_PLAYER:
        return {"min": None, "max": None}

    player = game.game.players[HUMAN_PLAYER]
    legal = game.legal_actions(HUMAN_PLAYER)
    if not any(action.action_type == ActionType.RAISE for action in legal):
        return {"min": None, "max": None}

    return {
        "min": game.current_bet + game.min_raise,
        "max": player.bet + player.chips.total(),
    }


def state_payload() -> dict[str, Any]:
    game = ensure_game()
    public = game.public_state_for(HUMAN_PLAYER)

    players = []
    for player in public["players"]:
        players.append({
            **player,
            "hand": [card_payload(card) for card in player["hand"]],
        })

    return {
        "phase": public["phase"],
        "pot": public["pot"],
        "community_cards": [card_payload(card) for card in public["community_cards"]],
        "dealer_index": public["dealer_index"],
        "current_player": public["current_player"],
        "current_bet": public["current_bet"],
        "min_raise": public["min_raise"],
        "players": players,
        "legal_actions": [action_payload(action) for action in public["legal_actions"]],
        "raise_bounds": raise_bounds(),
        "terminal": public["terminal"],
        "winners": public["winners"],
        "chip_deltas": game.chip_deltas() if game.hand_over else {},
        "model_loaded": model is not None,
    }


@app.get("/")
def index():
    return send_from_directory("web/static", "index.html")


@app.get("/api/state")
def get_state():
    return jsonify(state_payload())


@app.post("/api/new-hand")
def new_hand():
    global engine
    current = ensure_game()
    if current.hand_over:
        current.next_round()
    engine = current
    if not engine.hand_started:
        engine.start_hand()
    autoplay_rl()
    return jsonify(state_payload())


@app.post("/api/action")
def submit_action():
    game = ensure_game()
    if game.hand_over:
        return jsonify(state_payload())
    if game.current_actor != HUMAN_PLAYER:
        autoplay_rl()
        return jsonify(state_payload())

    data = request.get_json(force=True)
    action_type = data.get("type")
    amount = data.get("amount")
    raw = f"raise {amount}" if action_type == "raise" else str(action_type)
    game.step(parse_action(raw))
    autoplay_rl()
    return jsonify(state_payload())


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
