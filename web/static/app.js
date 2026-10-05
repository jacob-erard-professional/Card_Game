import { createTable, DENOMINATIONS, chipLabel } from "./table3d.js";

const HUMAN = 0;
const BOT = 1;
const NAMES = { 0: "You", 1: "RL Model" };
const PHASE_NAMES = { preflop: "Preflop", flop: "Flop", turn: "Turn", river: "River" };
const CARD_STAGGER_MS = 170;

const ui = {
  frame: null,
  busy: false,
  thinking: false,
  raiseOpen: false,
  raiseTarget: 0,
};

const suitSymbols = {
  hearts: "♥",
  diamonds: "♦",
  clubs: "♣",
  spades: "♠",
};

const money = (value) => `$${Number(value || 0).toLocaleString()}`;
const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));
const between = (low, high) => low + Math.random() * (high - low);
const $ = (id) => document.getElementById(id);
const playerIn = (frame, seat) => frame.players.find((player) => player.seat === seat);
const cardKey = (card) => `${card.rank}-${card.suit}-${card.value}`;

const table = createTable($("scene"));

// ---------- Server ----------

async function request(path, options = {}) {
  ui.busy = true;
  renderDock(ui.frame);
  try {
    const response = await fetch(path, options);
    const body = await response.json();
    await playTimeline(body.timeline || []);
    if (body.error) flashStatus(body.error);
  } catch (error) {
    console.error(error);
    flashStatus("Lost the server. Is web_app.py still running?");
  } finally {
    ui.busy = false;
    renderDock(ui.frame);
  }
}

function deal() {
  hideWinBanner();
  return request("/api/deal", { method: "POST" });
}

function newMatch() {
  ui.frame = null;
  hideWinBanner();
  hideSpeech(HUMAN);
  hideSpeech(BOT);
  return request("/api/new-match", { method: "POST" });
}

function submitAction(action) {
  if (ui.busy) return;
  closeRaise();
  pulseAction(action.type);
  request("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(action),
  });
}

// ---------- Timeline playback ----------

// Replays each engine step the server sent: the bot pauses to think, chips move, cards deal,
// and a finished hand pushes the pot to the winner before announcing them.
async function playTimeline(frames) {
  const quiet = ui.frame === null && frames.length === 1;
  for (const frame of frames) {
    const previous = ui.frame;
    const sameHand = Boolean(previous) && previous.hand_number === frame.hand_number;
    const fresh = newEntries(previous, frame).filter((entry) => entry.action !== "post");
    const botMove = fresh.find((entry) => entry.seat === BOT);
    if (botMove && !quiet) await think(botMove);

    if (!quiet) {
      fresh.forEach((entry) => {
        showSpeech(entry.seat, describe(entry));
        if (entry.action === "check") table.tap(entry.seat);
      });
    }
    const handEnds = sameHand && frame.terminal && !previous.terminal;
    if (sameHand && !quiet) await moveChips(previous, frame);

    ui.frame = frame;
    render(frame, previous, { holdPot: handEnds });

    const newCards = sameHand ? frame.community_cards.length - previous.community_cards.length : 0;
    if (newCards > 0) await sleep(newCards * CARD_STAGGER_MS + (frame.terminal ? 700 : 450));

    if (handEnds) {
      await sleep(350);
      await pushPotToWinners(frame);
      showWinBanner(frame);
    } else if (frame.terminal && quiet) {
      showWinBanner(frame);
    }
  }
}

function newEntries(previous, frame) {
  const annotated = annotate(frame.action_log);
  if (!previous || previous.hand_number !== frame.hand_number) return annotated;
  return annotated.slice(previous.action_log.length);
}

async function think(entry) {
  const aggressive = entry.action === "raise" || entry.action === "allin";
  ui.thinking = true;
  renderDock(ui.frame);
  table.robot.mood("thinking");
  showSpeech(BOT, "", true);
  await sleep(aggressive ? between(1100, 1700) : between(650, 1150));
  table.robot.mood("idle");
  ui.thinking = false;
}

// Works out call sizes and bet-vs-raise wording by replaying the hand's log.
function annotate(log) {
  let phase = null;
  let bets = {};
  let streetBet = 0;
  return log.map((entry) => {
    if (entry.phase !== phase) {
      phase = entry.phase;
      bets = {};
      streetBet = 0;
    }
    const prior = bets[entry.seat] || 0;
    const annotated = { ...entry, added: entry.total_bet - prior, opened: streetBet === 0 };
    bets[entry.seat] = entry.total_bet;
    streetBet = Math.max(streetBet, entry.total_bet);
    return annotated;
  });
}

function describe(entry) {
  switch (entry.action) {
    case "post": return `Posts ${money(entry.added)}`;
    case "fold": return "Fold";
    case "check": return "Check";
    case "call": return `Call ${money(entry.added)}`;
    case "raise": return entry.opened ? `Bet ${money(entry.total_bet)}` : `Raise to ${money(entry.total_bet)}`;
    case "allin": return `All in ${money(entry.total_bet)}`;
    default: return entry.action;
  }
}

// ---------- Chip movement ----------

// Chips go from each player's stack to their bet; if the street closed, every bet then sweeps into the pot.
async function moveChips(previous, frame) {
  const streetClosed = frame.phase !== previous.phase || frame.terminal;
  const betsNow = {};
  const throws = [];

  frame.players.forEach((player) => {
    const seat = player.seat;
    const before = playerIn(previous, seat);
    const added = player.committed - before.committed;
    betsNow[seat] = streetClosed ? before.bet + Math.max(0, added) : player.bet;
    if (added <= 0) return;
    const onGrab = () => {
      countTo($(`stack-${seat}`), before.chips - added);
      table.setStack(seat, before.chips - added);
    };
    throws.push(table.carry(seat, { pile: seat }, { bet: seat }, added, { onGrab }).then(() => setBet(seat, betsNow[seat])));
  });
  await Promise.all(throws);
  if (!streetClosed) return;

  const sweeping = Object.entries(betsNow).filter(([, amount]) => amount > 0);
  if (!sweeping.length) return;
  await sleep(180);
  const swept = previousSweptPot(previous) + sweeping.reduce((sum, [, amount]) => sum + amount, 0);
  await Promise.all(sweeping.map(([seat, amount]) => {
    setBet(Number(seat), 0);
    return table.flyChips({ bet: Number(seat) }, "pot", amount, { arc: 0.06 });
  }));
  setPot(swept, swept);
  bump($("potLabel"));
}

function previousSweptPot(frame) {
  return frame.pot - frame.players.reduce((sum, player) => sum + player.bet, 0);
}

// Each winner reaches in and drags their share of the pot back to their stack.
async function pushPotToWinners(frame) {
  const pushes = frame.results.filter((result) => result.won > 0).map((result) => {
    const before = playerIn(frame, result.seat).chips - result.won;
    return table.carry(result.seat, "pot", { pile: result.seat }, result.won, { onGrab: () => setPot(0, 0) })
      .then(() => {
        countTo($(`stack-${result.seat}`), before + result.won, 600);
        table.setStack(result.seat, before + result.won);
        bump($(`plate-${result.seat}`));
      });
  });
  await Promise.all(pushes);
}

function chipElement(value, color, stripe) {
  const chip = document.createElement("span");
  chip.className = "chip";
  chip.dataset.value = chipLabel(value);
  chip.style.setProperty("--chip", color);
  chip.style.setProperty("--stripe", stripe);
  return chip;
}

function countTo(el, target, duration = 350) {
  const start = Number(el.dataset.value ?? 0);
  el.dataset.value = String(target);
  if (start === target) {
    el.textContent = money(target);
    return;
  }
  const began = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - began) / duration);
    const eased = 1 - (1 - t) ** 3;
    el.textContent = money(Math.round(start + (target - start) * eased));
    if (t < 1 && el.dataset.value === String(target)) window.requestAnimationFrame(step);
  };
  window.requestAnimationFrame(step);
}

function setStack(seat, amount) {
  const el = $(`stack-${seat}`);
  el.dataset.value = String(amount);
  el.textContent = money(amount);
  table.setStack(seat, amount);
}

function setBet(seat, amount) {
  $(`betAmt-${seat}`).textContent = money(amount);
  $(`bet-${seat}`).classList.toggle("empty", !amount);
  table.setBet(seat, amount);
}

function setPot(total, swept) {
  $("pot").textContent = money(total);
  $("potLabel").classList.toggle("empty", !total);
  table.setPot(swept);
}

function bump(el) {
  if (!el) return;
  el.animate(
    [{ transform: "scale(1)" }, { transform: "scale(1.08)" }, { transform: "scale(1)" }],
    { duration: 260, easing: "ease-out" },
  );
}

// ---------- Table rendering ----------

function render(data, previous, { holdPot = false } = {}) {
  $("modelStatus").textContent = data.model_loaded ? "Trained policy loaded" : "Fallback policy";
  $("phase").textContent = PHASE_NAMES[data.phase] || data.phase;
  $("blinds").textContent = `Blinds ${money(data.blinds.small)}/${money(data.blinds.big)}`;

  const newHand = !previous || previous.hand_number !== data.hand_number;
  if (newHand) {
    hideSpeech(HUMAN);
    hideSpeech(BOT);
    hideWinBanner();
  }

  // While a finished hand is being animated, show the pot still on the table and winners' stacks without it.
  const potOnTable = data.players.reduce((sum, player) => sum + player.committed, 0);
  const wonBy = Object.fromEntries(data.results.map((result) => [result.seat, result.won]));
  const betsTotal = data.players.reduce((sum, player) => sum + player.bet, 0);
  if (holdPot) {
    setPot(potOnTable, potOnTable);
  } else if (data.terminal) {
    setPot(0, 0);
  } else {
    setPot(data.pot, Math.max(0, data.pot - betsTotal));
  }

  data.players.forEach((player) => {
    const seat = player.seat;
    setStack(seat, holdPot ? player.chips - (wonBy[seat] || 0) : player.chips);
    // Finished hands have no live bets: everything went to the pot and then to the winner.
    setBet(seat, holdPot || data.terminal ? 0 : player.bet);
    table.setHand(seat, player.hand, {
      hidden: seat === BOT && !player.hand.length && !player.folded,
      folded: player.folded,
      round: data.hand_number,
      delay: seat === HUMAN ? 0 : CARD_STAGGER_MS,
      stagger: CARD_STAGGER_MS,
    });
    $(`label-${seat}`).textContent = player.hand_description || "";
    $(`label-${seat}`).classList.toggle("win", data.terminal && data.winners.includes(seat));
    const plate = $(`plate-${seat}`);
    plate.classList.toggle("active", !data.terminal && data.current_player === seat);
    plate.classList.toggle("folded", player.folded);
    plate.classList.toggle("winner", data.terminal && data.winners.includes(seat));
  });

  table.setBoard(data.community_cards, { stagger: newHand ? 0 : CARD_STAGGER_MS });
  table.setActive(data.terminal ? null : data.current_player);
  table.setDealer(data.dealer_index);
  table.highlight(data.terminal ? new Set(data.results.flatMap((result) => (result.best_cards || []).map(cardKey))) : null);
  table.robot.mood(robotMood(data));
  renderStatus(data);
  renderDock(data);
  renderLog(data);
}

// The robot gloats when it wins, sulks when it loses, and slumps back after folding.
function robotMood(data) {
  const botWon = data.winners.includes(BOT);
  const youWon = data.winners.includes(HUMAN);
  if (data.terminal && botWon !== youWon) return botWon ? "happy" : "sad";
  return playerIn(data, BOT).folded ? "folded" : "idle";
}

function renderStatus(data) {
  // The banner announces results and the buttons say what's possible; this line is only for errors.
  if (!$("turnStatus").classList.contains("error")) $("dockStatus").hidden = true;
}

function winnerSummary(data) {
  const human = data.results.find((result) => result.seat === HUMAN);
  const split = data.results.length > 1;
  const top = data.results[0];
  const change = Number(data.chip_deltas?.[HUMAN] || 0);
  let title;
  let tone;
  if (split) {
    title = "Split pot";
    tone = "split";
  } else if (human) {
    title = "You win!";
    tone = "you";
  } else {
    title = "RL Model wins";
    tone = "bot";
  }
  let eyebrow = `Hand #${data.hand_number}`;
  if (data.match_over) {
    const alive = playerIn(data, HUMAN).chips > 0;
    title = alive ? "You win the match!" : "RL Model wins the match";
    eyebrow = alive ? "Match over · you busted the RL Model" : "Match over · you're out of chips";
  }
  // Same kind of hand on both sides reads like a bug unless we say what actually split them.
  let hand = "Everyone else folded";
  if (top?.description) {
    hand = split ? `Split · both play ${top.description}` : top.description;
    if (!split && top.decided_by) hand += ` · wins on ${top.decided_by}`;
  }
  const loser = !split && top?.description
    ? data.players.find((player) => player.seat !== top.seat && player.best_cards)
    : null;
  const won = data.results.reduce((sum, result) => sum + result.won, 0);
  return { title, tone, eyebrow, hand, won, change, cards: top?.best_cards || [], loser };
}

function showWinBanner(data) {
  const summary = winnerSummary(data);
  const banner = $("winBanner");
  banner.className = `win-banner ${summary.tone}`;
  $("winEyebrow").textContent = summary.eyebrow;
  $("winTitle").textContent = summary.title;
  const amounts = {
    you: `+${money(summary.change)}`,
    split: `${money(summary.won)} pot split`,
    // Heads-up, the bot's net is exactly what you lost (an uncalled bet just comes back).
    bot: `+${money(-summary.change)}`,
  };
  $("winAmount").textContent = amounts[summary.tone];
  $("winHand").textContent = summary.hand;
  const cards = $("winCards");
  cards.innerHTML = "";
  summary.cards.forEach((card) => cards.appendChild(cardElement(card)));
  // The losing hand's best five underneath, so you can see exactly what it was up against.
  const vs = $("winVs");
  vs.hidden = !summary.loser;
  if (summary.loser) {
    $("winVsLabel").textContent = `${NAMES[summary.loser.seat]} · ${summary.loser.hand_description}`;
    const loserCards = $("winVsCards");
    loserCards.innerHTML = "";
    summary.loser.best_cards.forEach((card) => loserCards.appendChild(cardElement(card)));
  }
  banner.hidden = false;
  banner.animate(
    [
      { transform: "translate(-50%, -50%) scale(0.7)", opacity: 0 },
      { transform: "translate(-50%, -50%) scale(1.05)", opacity: 1, offset: 0.7 },
      { transform: "translate(-50%, -50%) scale(1)", opacity: 1 },
    ],
    { duration: 420, easing: "cubic-bezier(0.2, 0.9, 0.3, 1.2)" },
  );
  if (summary.tone === "you") celebrate(banner);
}

function hideWinBanner() {
  $("winBanner").hidden = true;
}

// A burst of chips out of the banner when you win.
function celebrate(banner) {
  const box = banner.getBoundingClientRect();
  const cx = box.left + box.width / 2 - 13;
  const cy = box.top + box.height / 2 - 13;
  for (let i = 0; i < 22; i += 1) {
    const [value, color, stripe] = DENOMINATIONS[i % DENOMINATIONS.length];
    const chip = chipElement(value, color, stripe);
    chip.classList.add("flying");
    document.body.appendChild(chip);
    const angle = (i / 22) * Math.PI * 2 + between(-0.2, 0.2);
    const distance = between(140, 260);
    const x = cx + Math.cos(angle) * distance;
    const y = cy + Math.sin(angle) * distance * 0.6;
    chip.animate(
      [
        { transform: `translate(${cx}px, ${cy}px) scale(0.6) rotate(0deg)`, opacity: 1 },
        { transform: `translate(${x}px, ${y}px) scale(1) rotate(${between(-360, 360)}deg)`, opacity: 1, offset: 0.7 },
        { transform: `translate(${x}px, ${y + 40}px) scale(0.9)`, opacity: 0 },
      ],
      { duration: 1100, delay: i * 12, easing: "cubic-bezier(0.15, 0.8, 0.3, 1)", fill: "forwards" },
    ).finished.then(() => chip.remove());
  }
}

// Flat cards for the win banner.
function cardElement(card) {
  const el = document.createElement("div");
  el.className = "card";
  const suit = suitSymbols[card.suit] || card.suit;
  if (card.suit === "hearts" || card.suit === "diamonds") el.classList.add("red");
  el.innerHTML = `<span class="rank">${card.rank}</span><span class="center">${suit}</span><span class="suit">${suit}</span>`;
  return el;
}

// ---------- Action dock ----------

function renderDock(data) {
  const dock = $("dockActions");
  dock.innerHTML = "";
  dock.hidden = false;
  if (!data) return;

  if (data.terminal) {
    closeRaise();
    if (ui.busy) return;
    const button = actionButton(data.match_over ? "New match" : "Deal next hand", "deal", "Space");
    button.addEventListener("click", data.match_over ? newMatch : deal);
    dock.appendChild(button);
    return;
  }

  if (data.current_player !== HUMAN || ui.busy) {
    closeRaise();
    const pill = document.createElement("div");
    pill.className = "thinking-pill";
    pill.innerHTML = ui.thinking || data.current_player === BOT
      ? `<span class="dots"><i></i><i></i><i></i></span> RL Model is thinking`
      : `<span class="dots"><i></i><i></i><i></i></span>`;
    dock.appendChild(pill);
    return;
  }

  // While sizing a raise the tray takes over the dock, so the buttons get out of the way.
  if (ui.raiseOpen) {
    dock.hidden = true;
    syncRaiseTray(data);
    return;
  }

  const legal = Object.fromEntries(data.legal_actions.map((action) => [action.type, action]));
  const me = playerIn(data, HUMAN);
  const toCall = data.current_bet - me.bet;

  if (legal.fold && toCall > 0) {
    dock.appendChild(actionButton("Fold", "fold", "F", () => submitAction({ type: "fold" })));
  }
  if (legal.check) {
    dock.appendChild(actionButton("Check", "check", "C", () => submitAction({ type: "check" })));
  } else if (legal.call) {
    const label = toCall >= me.chips ? `Call all in ${money(me.chips)}` : `Call ${money(toCall)}`;
    dock.appendChild(actionButton(label, "call", "C", () => submitAction({ type: "call" })));
  }

  if (data.raise_bounds.min !== null) {
    const verb = data.current_bet === 0 ? "Bet" : "Raise";
    dock.appendChild(actionButton(verb, "raise", "R", toggleRaise));
  } else if (legal.allin && me.chips > toCall) {
    dock.appendChild(actionButton(`All in ${money(me.bet + me.chips)}`, "allin", "A", () => submitAction({ type: "allin" })));
  }
}

function actionButton(label, type, key, onClick) {
  const button = document.createElement("button");
  button.className = `action action-${type}`;
  button.dataset.type = type;
  button.innerHTML = `<span>${label}</span><kbd>${key}</kbd>`;
  if (onClick) button.addEventListener("click", onClick);
  return button;
}

function toggleRaise() {
  if (ui.raiseOpen) {
    closeRaise();
  } else {
    openRaise();
  }
  renderDock(ui.frame);
}

function openRaise() {
  const data = ui.frame;
  if (!data || data.raise_bounds.min === null) return;
  ui.raiseOpen = true;
  ui.raiseTarget = data.raise_bounds.min;
  $("raiseTray").hidden = false;
  syncRaiseTray(data);
  $("raiseSlider").focus();
}

function closeRaise() {
  ui.raiseOpen = false;
  $("raiseTray").hidden = true;
}

function syncRaiseTray(data) {
  const { min, max } = data.raise_bounds;
  const slider = $("raiseSlider");
  slider.min = String(min);
  slider.max = String(max);
  slider.step = String(Math.max(1, Math.floor(data.blinds.small / 2)));
  ui.raiseTarget = Math.min(max, Math.max(min, ui.raiseTarget));
  slider.value = String(ui.raiseTarget);
  slider.style.setProperty("--fill", `${max > min ? ((ui.raiseTarget - min) / (max - min)) * 100 : 100}%`);

  const verb = data.current_bet === 0 ? "Bet" : "Raise to";
  const allIn = ui.raiseTarget >= max;
  $("raiseAmount").textContent = money(ui.raiseTarget);
  $("raiseTray").querySelector(".raise-readout span").textContent = allIn ? "All in for" : verb;
  $("confirmRaise").innerHTML = `${allIn ? "All in" : verb.replace(" to", "")} ${money(ui.raiseTarget)} <kbd>↵</kbd>`;
  $("presets").querySelectorAll("button").forEach((button) => {
    button.classList.toggle("selected", presetTarget(data, button.dataset.preset) === ui.raiseTarget);
  });
}

function presetTarget(data, preset) {
  const { min, max } = data.raise_bounds;
  const me = playerIn(data, HUMAN);
  const toCall = data.current_bet - me.bet;
  // A pot-sized raise is the call plus the pot as it stands after calling.
  const potRaise = (fraction) => Math.round(data.current_bet + (data.pot + toCall) * fraction);
  const targets = { min, half: potRaise(0.5), pot: potRaise(1), max };
  return Math.min(max, Math.max(min, targets[preset]));
}

function confirmRaise() {
  if (!ui.raiseOpen || !ui.frame) return;
  submitAction({ type: "raise", amount: ui.raiseTarget });
}

$("raiseSlider").addEventListener("input", (event) => {
  ui.raiseTarget = Number(event.target.value);
  syncRaiseTray(ui.frame);
});
$("presets").addEventListener("click", (event) => {
  const preset = event.target.closest("button")?.dataset.preset;
  if (!preset || !ui.frame) return;
  ui.raiseTarget = presetTarget(ui.frame, preset);
  syncRaiseTray(ui.frame);
});
$("confirmRaise").addEventListener("click", confirmRaise);
$("cancelRaise").addEventListener("click", () => {
  closeRaise();
  renderDock(ui.frame);
});

document.addEventListener("keydown", (event) => {
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  const key = event.key.toLowerCase();
  if (key === "v" && !ui.raiseOpen) {
    table.toggleView();
    return;
  }
  if (key === "escape" && !ui.raiseOpen && table.inTopView()) {
    table.leaveTopView();
    return;
  }
  if (!ui.frame || ui.busy) return;
  const data = ui.frame;

  if (data.terminal) {
    if (key === " " || key === "enter") {
      event.preventDefault();
      (data.match_over ? newMatch : deal)();
    }
    return;
  }
  if (data.current_player !== HUMAN) return;

  if (ui.raiseOpen) {
    if (key === "enter") {
      event.preventDefault();
      confirmRaise();
    } else if (key === "escape") {
      closeRaise();
      renderDock(data);
    }
    return;
  }

  const button = {
    f: "fold", c: data.legal_actions.some((a) => a.type === "check") ? "check" : "call", r: "raise", a: "allin",
  }[key];
  const target = button && document.querySelector(`#dockActions [data-type="${button}"]`);
  if (target) {
    event.preventDefault();
    target.click();
  }
});

// ---------- Hand log drawer ----------

function renderLog(data) {
  $("currentHandTitle").textContent = `Hand #${data.hand_number}`;
  $("currentLog").innerHTML = logItems(data.action_log);
  $("history").innerHTML = data.history
    .filter((hand) => !(hand.number === data.hand_number && !data.terminal))
    .map(historyItem)
    .join("") || `<p class="empty-note">No finished hands yet.</p>`;
}

function logItems(log) {
  let phase = null;
  return annotate(log).map((entry) => {
    const header = entry.phase !== phase ? `<li class="street">${PHASE_NAMES[entry.phase]}</li>` : "";
    phase = entry.phase;
    const who = `<b class="${entry.seat === HUMAN ? "you" : "bot"}">${NAMES[entry.seat]}</b>`;
    return `${header}<li>${who} ${describe(entry).toLowerCase()}</li>`;
  }).join("");
}

function historyItem(hand) {
  const delta = Number(hand.chip_deltas[HUMAN] || 0);
  const summary = hand.results.map((result) => `${NAMES[result.seat]} won ${money(result.won)}${result.description ? ` · ${result.description}` : ""}${result.decided_by ? ` (${result.decided_by})` : ""}`).join(", ");
  const board = hand.board.length ? hand.board.map(cardText).join(" ") : "No flop";
  const shown = hand.shown.map((s) => `<div>${NAMES[s.seat]}: ${s.cards.map(cardText).join(" ")} <span class="muted">(${s.hand_name})</span></div>`).join("");
  return `
    <details class="history-item">
      <summary>
        <span>#${hand.number}</span>
        <span class="summary-text">${summary}</span>
        <span class="${delta >= 0 ? "win" : "loss"}">${delta >= 0 ? "+" : "−"}${money(Math.abs(delta))}</span>
      </summary>
      <div class="history-body">
        <div>Board: ${board}</div>
        ${shown}
        <ol class="log">${logItems(hand.actions)}</ol>
      </div>
    </details>`;
}

function cardText(card) {
  const suit = suitSymbols[card.suit] || card.suit;
  const red = card.suit === "hearts" || card.suit === "diamonds";
  return `<span class="card-text${red ? " red" : ""}">${card.rank}${suit}</span>`;
}

function setDrawer(open) {
  $("drawer").hidden = !open;
  $("logToggle").setAttribute("aria-expanded", String(open));
}

$("logToggle").addEventListener("click", () => setDrawer($("drawer").hidden));
$("viewToggle").addEventListener("click", () => table.toggleView());
table.onViewChange((top) => {
  $("viewToggle").innerHTML = top ? "Back to seat <kbd>V</kbd>" : "Bird's-eye <kbd>V</kbd>";
});
$("logClose").addEventListener("click", () => setDrawer(false));
$("newMatch").addEventListener("click", () => {
  if (!ui.busy) newMatch();
});

// ---------- Effects ----------

function flashStatus(text) {
  const status = $("turnStatus");
  $("dockStatus").hidden = false;
  status.textContent = text;
  status.classList.add("error");
  status.classList.remove("shake");
  void status.offsetWidth;
  status.classList.add("shake");
  window.setTimeout(() => {
    status.classList.remove("error");
    $("dockStatus").hidden = true;
  }, 4000);
}

function pulseAction(type) {
  const active = document.querySelector(`#dockActions [data-type="${type}"], #confirmRaise`);
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

function showSpeech(seat, text, thinking = false) {
  const bubble = $(`speech-${seat}`);
  bubble.classList.toggle("thinking-bubble", thinking);
  bubble.innerHTML = thinking ? `<span class="dots"><i></i><i></i><i></i></span>` : "";
  if (!thinking) bubble.textContent = text;
  bubble.classList.remove("show");
  void bubble.offsetWidth;
  bubble.classList.add("show");
}

function hideSpeech(seat) {
  $(`speech-${seat}`).classList.remove("show");
}

request("/api/state");
