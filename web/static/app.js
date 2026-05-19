const state = {
  latest: null,
  lastUserAction: null,
  lastRlAction: null,
};

const suitSymbols = {
  hearts: "♥",
  diamonds: "♦",
  clubs: "♣",
  spades: "♠",
};

const money = (value) => `$${Number(value || 0).toLocaleString()}`;

function cardElement(card, hidden = false) {
  const el = document.createElement("div");
  el.className = "card";

  if (hidden) {
    el.classList.add("back");
    el.innerHTML = `<span class="rank">RL</span><span class="center">◆</span><span class="suit">◆</span>`;
    return el;
  }

  if (!card) {
    el.classList.add("placeholder");
    el.innerHTML = `<span class="rank"></span><span class="center">•</span><span class="suit"></span>`;
    return el;
  }

  const suit = suitSymbols[card.suit] || card.suit;
  if (card.suit === "hearts" || card.suit === "diamonds") {
    el.classList.add("red");
  }
  el.innerHTML = `<span class="rank">${card.rank}</span><span class="center">${suit}</span><span class="suit">${suit}</span>`;
  return el;
}

function renderCards(target, cards, count, hidden = false) {
  for (let i = 0; i < count; i += 1) {
    const card = cards[i];
    const isHiddenBack = hidden && !card;
    const key = card
      ? `${card.rank}-${card.suit}-${card.value}`
      : isHiddenBack
        ? `back-${target.id}-${i}`
        : `empty-${target.id}-${i}`;

    const existing = target.children[i];
    if (existing?.dataset.cardKey === key) {
      continue;
    }

    const next = cardElement(card, isHiddenBack);
    next.dataset.cardKey = key;
    const shouldDeal = card || isHiddenBack;
    if (shouldDeal) {
      next.style.visibility = "hidden";
    }

    if (existing) {
      target.replaceChild(next, existing);
    } else {
      target.appendChild(next);
    }

    if (shouldDeal) {
      dealCardTo(next);
    }
  }

  while (target.children.length > count) {
    target.removeChild(target.lastElementChild);
  }
}

function renderActions(data) {
  const actions = document.getElementById("actions");
  const betBuilder = document.getElementById("betBuilder");
  actions.innerHTML = "";
  betBuilder.hidden = true;

  if (data.terminal) {
    const button = document.createElement("button");
    button.className = "primary";
    button.textContent = "Deal Next Hand";
    button.addEventListener("click", newHand);
    actions.appendChild(button);
    return;
  }

  if (data.current_player !== 0) {
    const button = document.createElement("button");
    button.disabled = true;
    button.textContent = "RL Thinking";
    actions.appendChild(button);
    return;
  }

  data.legal_actions
    .filter((action) => action.type !== "raise")
    .forEach((action) => {
    const button = document.createElement("button");
    button.dataset.type = action.type;
    if (action.type === "fold") button.className = "danger";
    if (action.type === "call" || action.type === "check") button.className = "primary";
    button.textContent = labelForAction(action);
    button.addEventListener("click", () => submitAction(action));
    actions.appendChild(button);
  });

  const canRaise = data.raise_bounds?.min !== null && data.raise_bounds?.max !== null;
  if (canRaise) {
    renderBetBuilder(data);
  }
}

function labelForAction(action) {
  if (action.type === "allin") return "All In";
  return action.type.charAt(0).toUpperCase() + action.type.slice(1);
}

function render(data) {
  const previous = state.latest;
  updateDialogue(previous, data);
  state.latest = data;
  document.getElementById("modelStatus").textContent = data.model_loaded
    ? "Trained policy loaded"
    : "RL fallback policy";
  document.getElementById("phase").textContent = data.phase;
  document.getElementById("pot").textContent = money(data.pot);

  data.players.forEach((player) => {
    document.getElementById(`stack-${player.player_num}`).textContent = money(player.chips);
    document.getElementById(`bet-${player.player_num}`).textContent = money(player.bet);
    const handEl = document.getElementById(`hand-${player.player_num}`);
    renderCards(handEl, player.hand, 2, player.player_num === 1 && !data.terminal);
    document.getElementById(`seat-${player.player_num}`).classList.toggle(
      "active",
      data.current_player === player.player_num,
    );
    document.getElementById(`seat-${player.player_num}`).classList.toggle(
      "winner",
      data.terminal && data.winners.includes(player.player_num),
    );
  });

  renderCards(document.getElementById("community"), data.community_cards, 5);
  renderStatus(data);
  renderActions(data);
  animateStateChange(previous, data);
}

function renderStatus(data) {
  const turn = document.getElementById("turnStatus");
  const delta = document.getElementById("deltaStatus");
  delta.className = "";
  delta.textContent = "";

  if (data.terminal) {
    const won = data.winners.includes(0);
    turn.textContent = won ? "You won the hand" : "RL model won the hand";
    const change = Number(data.chip_deltas?.[0] || 0);
    delta.textContent = `${change >= 0 ? "+" : ""}${money(change)}`;
    delta.classList.add(change >= 0 ? "win" : "loss");
    return;
  }

  turn.textContent = data.current_player === 0 ? "Your move" : "RL model is acting";
  delta.textContent = `Current bet ${money(data.current_bet)}`;
}

async function fetchState() {
  const response = await fetch("/api/state");
  render(await response.json());
}

async function submitAction(action) {
  state.lastUserAction = labelForAction(action);
  showSpeech(0, state.lastUserAction);
  pulseAction(action.type);
  const response = await fetch("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(action),
  });
  render(await response.json());
}

async function newHand() {
  state.latest = null;
  state.lastUserAction = null;
  state.lastRlAction = null;
  hideSpeech(0);
  hideSpeech(1);
  const response = await fetch("/api/new-hand", { method: "POST" });
  render(await response.json());
}

document.getElementById("newHand").addEventListener("click", newHand);
document.getElementById("halfPot").addEventListener("click", () => setRaisePreset(0.5));
document.getElementById("potBet").addEventListener("click", () => setRaisePreset(1));
document.getElementById("maxBet").addEventListener("click", () => setRaiseMax());
document.getElementById("submitRaise").addEventListener("click", submitCustomRaise);
fetchState();

function renderBetBuilder(data) {
  const betBuilder = document.getElementById("betBuilder");
  const input = document.getElementById("raiseAmount");
  const min = Number(data.raise_bounds.min);
  const max = Number(data.raise_bounds.max);
  betBuilder.hidden = false;
  input.min = String(min);
  input.max = String(max);
  input.placeholder = `${money(min)} to ${money(max)}`;
  if (!input.value || Number(input.value) < min || Number(input.value) > max) {
    input.value = String(min);
  }
}

function setRaisePreset(multiplier) {
  const data = state.latest;
  if (!data?.raise_bounds) return;
  const min = Number(data.raise_bounds.min);
  const max = Number(data.raise_bounds.max);
  const target = Math.round(Math.max(min, data.current_bet + data.pot * multiplier));
  document.getElementById("raiseAmount").value = String(Math.min(max, target));
}

function setRaiseMax() {
  const data = state.latest;
  if (!data?.raise_bounds) return;
  document.getElementById("raiseAmount").value = String(data.raise_bounds.max);
}

function submitCustomRaise() {
  const data = state.latest;
  if (!data?.raise_bounds) return;
  const input = document.getElementById("raiseAmount");
  const amount = Math.round(Number(input.value));
  const min = Number(data.raise_bounds.min);
  const max = Number(data.raise_bounds.max);
  if (!Number.isFinite(amount) || amount < min || amount > max) {
    input.classList.remove("shake");
    void input.offsetWidth;
    input.classList.add("shake");
    return;
  }
  submitAction({ type: "raise", amount });
}

function pulseAction(type) {
  const active = [...document.querySelectorAll(".actions button, .bet-builder button")]
    .find((button) => button.textContent.toLowerCase().includes(type));
  if (!active) return;
  active.animate(
    [
      { transform: "translateY(0) scale(1)" },
      { transform: "translateY(-2px) scale(1.04)" },
      { transform: "translateY(0) scale(1)" },
    ],
    { duration: 220, easing: "ease-out" },
  );
}

function animateStateChange(previous, next) {
  if (!previous) return;

  next.players.forEach((player) => {
    const before = previous.players.find((item) => item.player_num === player.player_num);
    if (!before) return;
    const committedDelta = Number(player.committed) - Number(before.committed);
    const betDelta = Number(player.bet) - Number(before.bet);
    if (committedDelta > 0 || betDelta > 0) {
      flyChipsFromSeat(player.player_num, Math.min(8, Math.max(3, Math.ceil((committedDelta || betDelta) / 20))));
      bumpBet(player.player_num);
    }
  });

  if (next.community_cards.length > previous.community_cards.length) {
    document.getElementById("community").animate(
      [
        { transform: "scale(0.98)", filter: "brightness(1)" },
        { transform: "scale(1.02)", filter: "brightness(1.25)" },
        { transform: "scale(1)", filter: "brightness(1)" },
      ],
      { duration: 420, easing: "ease-out" },
    );
  }

  if (!previous.terminal && next.terminal) {
    burstToWinner(next.winners[0] ?? 0);
  }
}

function bumpBet(playerNum) {
  const bet = document.getElementById(`bet-${playerNum}`);
  bet.classList.remove("bump");
  void bet.offsetWidth;
  bet.classList.add("bump");
  window.setTimeout(() => bet.classList.remove("bump"), 220);
}

function flyChipsFromSeat(playerNum, count) {
  const from = document.getElementById(`seat-${playerNum}`).getBoundingClientRect();
  const to = document.querySelector(".pot").getBoundingClientRect();
  const layer = document.body;

  for (let i = 0; i < count; i += 1) {
    const chip = document.createElement("span");
    chip.className = "chip-flight";
    const startX = from.left + from.width / 2 + (i - count / 2) * 8;
    const startY = from.top + from.height / 2;
    const endX = to.left + to.width / 2 + Math.sin(i) * 16;
    const endY = to.top + to.height / 2 + Math.cos(i) * 8;
    chip.style.setProperty("--from-x", `${startX}px`);
    chip.style.setProperty("--from-y", `${startY}px`);
    chip.style.setProperty("--to-x", `${endX}px`);
    chip.style.setProperty("--to-y", `${endY}px`);
    chip.style.animationDelay = `${i * 32}ms`;
    layer.appendChild(chip);
    chip.addEventListener("animationend", () => chip.remove());
  }
}

function burstToWinner(playerNum) {
  const seat = document.getElementById(`seat-${playerNum}`).getBoundingClientRect();
  const pot = document.querySelector(".pot").getBoundingClientRect();
  for (let i = 0; i < 14; i += 1) {
    const chip = document.createElement("span");
    chip.className = "chip-flight";
    chip.style.setProperty("--from-x", `${pot.left + pot.width / 2}px`);
    chip.style.setProperty("--from-y", `${pot.top + pot.height / 2}px`);
    chip.style.setProperty("--to-x", `${seat.left + seat.width / 2 + (Math.random() - 0.5) * 120}px`);
    chip.style.setProperty("--to-y", `${seat.top + seat.height / 2 + (Math.random() - 0.5) * 70}px`);
    chip.style.animationDelay = `${i * 26}ms`;
    document.body.appendChild(chip);
    chip.addEventListener("animationend", () => chip.remove());
  }
}

function updateDialogue(previous, next) {
  if (!previous) return;

  const beforeRl = previous.players.find((player) => player.player_num === 1);
  const afterRl = next.players.find((player) => player.player_num === 1);
  if (beforeRl && afterRl && !next.terminal) {
    const betDelta = Number(afterRl.committed) - Number(beforeRl.committed);
    if (afterRl.folded && !beforeRl.folded) {
      showSpeech(1, "Fold");
    } else if (betDelta > 0) {
      if (Number(afterRl.all_in) && Number(afterRl.chips) === 0) {
        showSpeech(1, "All in");
      } else if (Number(afterRl.bet) > Number(previous.current_bet)) {
        showSpeech(1, `Raise to ${money(afterRl.bet)}`);
      } else {
        showSpeech(1, `Call ${money(betDelta)}`);
      }
    } else if (previous.current_player === 1 && next.current_player === 0) {
      showSpeech(1, "Check");
    }
  }
}

function showSpeech(playerNum, text) {
  const bubble = document.getElementById(`speech-${playerNum}`);
  bubble.textContent = text;
  bubble.classList.remove("show");
  void bubble.offsetWidth;
  bubble.classList.add("show");
}

function hideSpeech(playerNum) {
  document.getElementById(`speech-${playerNum}`).classList.remove("show");
}

function dealCardTo(target) {
  window.requestAnimationFrame(() => {
    const deck = document.getElementById("deck");
    const deckRect = deck.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const flyer = target.cloneNode(true);
    flyer.classList.add("deal-flight");
    flyer.style.visibility = "visible";
    flyer.style.width = `${targetRect.width}px`;
    flyer.style.height = `${targetRect.height}px`;
    flyer.style.setProperty("--from-x", `${deckRect.left + deckRect.width / 2 - targetRect.width / 2}px`);
    flyer.style.setProperty("--from-y", `${deckRect.top + deckRect.height / 2 - targetRect.height / 2}px`);
    flyer.style.setProperty("--to-x", `${targetRect.left}px`);
    flyer.style.setProperty("--to-y", `${targetRect.top}px`);
    document.body.appendChild(flyer);
    flyer.addEventListener("animationend", () => {
      target.style.visibility = "visible";
      flyer.remove();
    });
  });
}
