import pytest

import web_app


@pytest.fixture
def client():
    web_app.table = None
    web_app.app.config.update(TESTING=True)
    with web_app.app.test_client() as client:
        yield client
    web_app.table = None


def latest(response):
    return response.get_json()["timeline"][-1]


def human_to_act(client):
    state = latest(client.get("/api/state"))
    for _ in range(20):
        if state["current_player"] == web_app.HUMAN_PLAYER:
            return state
        state = latest(client.post("/api/deal"))
    pytest.skip("RL opponent kept ending hands before the human acted")


@pytest.mark.parametrize("body", [
    {"type": "dance"},
    {"type": "raise"},
    {"type": "raise", "amount": "lots"},
    {"type": "raise", "amount": 1},
    [],
])
def test_bad_actions_return_400_with_state(client, body):
    human_to_act(client)
    response = client.post("/api/action", json=body)
    assert response.status_code == 400
    payload = response.get_json()
    assert payload["error"]
    assert payload["timeline"][-1]["players"]


def test_action_returns_one_frame_per_step(client):
    state = human_to_act(client)
    log_before = len(state["action_log"])
    action = next(a for a in state["legal_actions"] if a["type"] in ("check", "call"))

    response = client.post("/api/action", json={"type": action["type"]})

    assert response.status_code == 200
    timeline = response.get_json()["timeline"]
    first = timeline[0]
    assert first["action_log"][log_before]["seat"] == web_app.HUMAN_PLAYER
    for frame in timeline[1:]:
        assert frame["action_log"][-1]["seat"] == web_app.RL_PLAYER


def test_finished_hands_land_in_history(client):
    human_to_act(client)
    response = client.post("/api/action", json={"type": "fold"})
    frame = latest(response)
    assert frame["terminal"]
    assert frame["history"][0]["number"] == frame["hand_number"]
    assert frame["history"][0]["results"][0]["seat"] == web_app.RL_PLAYER

    next_hand = latest(client.post("/api/deal"))
    assert next_hand["hand_number"] == frame["hand_number"] + 1
