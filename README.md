# Card Game

A Python Texas Hold'em poker engine with a 3D browser table and reinforcement learning opponents. Play a heads-up match against the included policy, run automated games, or train bots through self-play.

## Setup

Use Python 3.10 or newer with a compatible PyTorch build. From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate the environment with `.venv\Scripts\activate` instead.

## Play in the browser

```sh
python web_app.py
```

Open <http://127.0.0.1:5050>. The table starts a two-player match with 1,000 chips per player. Use the table controls to act, deal another hand, or start a new match.

The opponent loads `rl/checkpoints/rl_2p.pt`. If PyTorch or the checkpoint is unavailable, it uses a simple opponent that prefers checking and calling. The browser needs WebGL and internet access to load Three.js from its CDN.

Set `PORT` to change the server port, or `FLASK_DEBUG=1` to enable Flask debug mode. This is a local demo: the server keeps one shared match in memory, so browser tabs share the same table and restarting the server resets it.

## Run automated games

```sh
python main.py
```

This runs up to 100 hands with 22 players using random legal actions, stopping if fewer than two players have chips.

## Train opponents

Bots use Neural Fictitious Self-Play (NFSP) in sit-and-go tournaments. Included policy checkpoints cover tables with two through five players.

```sh
python -m rl.train --players 2 3 4 5 --hands 300000
python -m rl.train --players 2 --hands 400000 --resume
```

`--hands` is the total training target; a resumed run trains the remaining hands. Use `--device cpu`, `--device mps`, or `--device cuda` to select a device, or leave the default `auto` selection. Run `python -m rl.train --help` for all options.

Training writes policies to `rl/checkpoints/rl_<n>p.pt` and resumable training state to `rl/checkpoints/rl_<n>p.train.pt`. Training state and logs are ignored by Git.

## Tests

```sh
python -m pip install -r requirements-dev.txt
python -m pytest
```

The suite covers hand evaluation, engine transitions, reinforcement learning components, and the web API.

## Project layout

- `engine.py`: poker rules, legal actions, and hand progression.
- `models/` and `actions/`: cards, players, game state, dealing, and showdown evaluation.
- `providers.py`: action providers for automated players.
- `web_app.py` and `web/static/`: Flask API and 3D browser interface.
- `rl/`: observations, policies, NFSP training, tournaments, and checkpoints.
- `tests/`: automated tests.
