from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request, send_from_directory

from actions.action import Action, ActionType
from engine import PokerEngine


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "web" / "static"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")

HUMAN_PLAYER = 0
RL_PLAYER = 1
HISTORY_LIMIT = 20


def load_model():
    """The heads-up NFSP policy, or None when torch or the checkpoint is missing."""
    try:
        from rl.policy import PolicyBot, checkpoint_path
    except ImportError:
        return None
    path = checkpoint_path(2)
    return PolicyBot.load(path) if path.exists() else None


def card_payload(card) -> dict[str, str | int]:
    rank_map = {11: "J", 12: "Q", 13: "K", 14: "A"}
    suit_map = {"H": "hearts", "D": "diamonds", "C": "clubs", "S": "spades"}
    value = card.rank.value
    return {
        "rank": rank_map.get(value, str(value)),
        "suit": suit_map.get(card.suit.value, card.suit.value),
        "value": value,
    }


def results_payload(results: list[dict]) -> list[dict]:
    return [
        {**r, "best_cards": [card_payload(c) for c in r["best_cards"]] if r["best_cards"] else None}
        for r in results
    ]


def action_payload(action: Action) -> dict[str, Any]:
    return {"type": action.action_type.value, "amount": action.amount}


class Table:
    """One heads-up match against the bot: the engine plus the hands played so far.

    Every request returns a timeline: one frame per engine step it caused, so the
    browser can replay the bot's moves one at a time instead of jumping to the end.
    """

    def __init__(self, bot):
        self.bot = bot
        self.engine = PokerEngine(num_players=2, blind_amount=20, starting_stack=1000)
        self.engine.game.players[HUMAN_PLAYER].name = "You"
        self.engine.game.players[RL_PLAYER].name = "RL Model"
        self.hand_number = 0
        self.history: list[dict] = []

    @property
    def match_over(self) -> bool:
        return len(self.engine.game.players_with_chips()) < 2

    def deal(self) -> list[dict]:
        """Start the next hand (if the last one is done) and play the bot until it's your turn."""
        if self.match_over:
            return [self.snapshot()]
        if self.engine.hand_over:
            self.engine.next_round()
        if not self.engine.hand_started:
            self.engine.start_hand()
            self.hand_number += 1
            self._record_finished_hand()
        return [self.snapshot(), *self._play_bot()]

    def act(self, action: Action) -> list[dict]:
        """Apply the human's action, then let the bot respond. Raises ValueError if illegal."""
        if self.engine.hand_over or self.engine.current_actor != HUMAN_PLAYER:
            raise ValueError("It is not your turn")
        self.engine.step(action)
        self._record_finished_hand()
        return [self.snapshot(), *self._play_bot()]

    def _play_bot(self) -> list[dict]:
        frames = []
        while not self.engine.hand_over and self.engine.current_actor == RL_PLAYER:
            self.engine.step(self._bot_action())
            self._record_finished_hand()
            frames.append(self.snapshot())
        return frames

    def _bot_action(self) -> Action:
        if self.bot is not None:
            return self.bot.act(self.engine, RL_PLAYER)
        legal = self.engine.legal_actions(RL_PLAYER)
        for preferred in (ActionType.CHECK, ActionType.CALL, ActionType.RAISE, ActionType.ALL_IN, ActionType.FOLD):
            for action in legal:
                if action.action_type == preferred:
                    return action
        raise RuntimeError("RL opponent has no legal action")

    def _record_finished_hand(self) -> None:
        engine = self.engine
        if not engine.hand_over or (self.history and self.history[0]["number"] == self.hand_number):
            return
        public = engine.public_state_for(HUMAN_PLAYER)
        self.history.insert(0, {
            "number": self.hand_number,
            "board": [card_payload(card) for card in public["community_cards"]],
            "results": results_payload(public["results"]),
            "shown": [
                {"seat": p["seat"], "cards": [card_payload(c) for c in p["hand"]], "hand_name": p["hand_description"]}
                for p in public["players"] if p["hand_name"]
            ],
            "actions": public["action_log"],
            "chip_deltas": engine.chip_deltas(),
        })
        del self.history[HISTORY_LIMIT:]

    def snapshot(self) -> dict[str, Any]:
        engine = self.engine
        public = engine.public_state_for(HUMAN_PLAYER)
        bounds = engine.raise_bounds(HUMAN_PLAYER)
        return {
            "hand_number": self.hand_number,
            "phase": public["phase"],
            "pot": public["pot"],
            "blinds": {"small": engine.game.blind_amount, "big": engine.game.blind_amount * 2},
            "community_cards": [card_payload(card) for card in public["community_cards"]],
            "dealer_index": public["dealer_index"],
            "current_player": public["current_player"],
            "current_bet": public["current_bet"],
            "min_raise": public["min_raise"],
            "players": [
                {
                    **p,
                    "hand": [card_payload(c) for c in p["hand"]],
                    "best_cards": [card_payload(c) for c in p["best_cards"]] if p["best_cards"] else None,
                }
                for p in public["players"]
            ],
            "legal_actions": [action_payload(action) for action in public["legal_actions"]],
            "raise_bounds": {"min": bounds[0], "max": bounds[1]} if bounds else {"min": None, "max": None},
            "terminal": public["terminal"],
            "winners": public["winners"],
            "results": results_payload(public["results"]),
            "chip_deltas": engine.chip_deltas() if engine.hand_over else {},
            "action_log": public["action_log"],
            "history": self.history,
            "match_over": self.match_over,
            "model_loaded": self.bot is not None,
        }


table: Table | None = None


def current_table() -> tuple[Table, list[dict] | None]:
    """Return the table, plus the opening timeline when a new match had to be started."""
    global table
    if table is None:
        table = Table(load_model())
        return table, table.deal()
    return table, None


@app.get("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/api/state")
def get_state():
    current, opening = current_table()
    return jsonify({"timeline": opening or [current.snapshot()]})


@app.post("/api/deal")
def deal():
    current, opening = current_table()
    return jsonify({"timeline": opening or current.deal()})


@app.post("/api/new-match")
def new_match():
    global table
    table = Table(load_model())
    return jsonify({"timeline": table.deal()})


@app.post("/api/action")
def submit_action():
    current, opening = current_table()
    if opening:
        return jsonify({"timeline": opening})
    try:
        timeline = current.act(parse_request_action(request.get_json(silent=True)))
    except ValueError as exc:
        return jsonify({"timeline": [current.snapshot()], "error": str(exc)}), 400
    return jsonify({"timeline": timeline})


def parse_request_action(data: Any) -> Action:
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object")
    try:
        action_type = ActionType(data.get("type"))
    except ValueError:
        raise ValueError(f"Unknown action type: {data.get('type')!r}") from None
    if action_type != ActionType.RAISE:
        return Action(action_type)
    amount = data.get("amount")
    if not isinstance(amount, int) or isinstance(amount, bool):
        raise ValueError("Raise requires an integer 'amount' (the raise-to total)")
    return Action.raise_to(amount)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5050"))  # macOS AirPlay Receiver holds 5000
    app.run(host="127.0.0.1", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
