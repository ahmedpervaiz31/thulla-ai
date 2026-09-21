import { gameStore } from "../state/gameStore.js";

/**
 * Bottom controls: play / step / auto + status.
 * @param {HTMLElement} root
 * @param {{ pacing?: boolean }} [opts]
 */
export function updateControlsBar(root, opts = {}) {
  const { game, selectedCard, autoEnabled, reviewMode } = gameStore.getSnapshot();
  const playBtn = root.querySelector('[data-role="play-btn"]');
  const stepBtn = root.querySelector('[data-role="step-btn"]');
  const autoBtn = root.querySelector('[data-role="auto-btn"]');
  const statusText = root.querySelector('[data-role="status-text"]');
  const sortSuit = root.querySelector('[data-role="sort-suit"]');
  const sortRank = root.querySelector('[data-role="sort-rank"]');

  if (!game) return;

  statusText.textContent = reviewMode
    ? `STATUS: REVIEW`
    : `STATUS: ${game.status}`;
  statusText.title = statusText.textContent;

  const isAi = game.mode === "ai";
  const hidePlay = isAi || reviewMode;
  stepBtn.classList.toggle("hidden", !isAi || reviewMode);
  autoBtn.classList.toggle("hidden", !isAi || reviewMode);
  playBtn.classList.toggle("hidden", hidePlay);
  autoBtn.classList.toggle("on", Boolean(autoEnabled) && !reviewMode);

  // Suit/rank sort is human-hand only.
  if (sortSuit) sortSuit.classList.toggle("hidden", isAi);
  if (sortRank) sortRank.classList.toggle("hidden", isAi);

  const awaiting =
    !reviewMode &&
    game.pending &&
    game.pending.type === "play" &&
    game.seats[game.pending.seat]?.is_human;
  const busy = Boolean(opts.pacing) || Boolean(opts.stepBusy) || reviewMode;
  playBtn.disabled = !(awaiting && selectedCard) || busy;
  stepBtn.disabled = busy;
  // Keep label width stable — selected card lives in the hand UI.
  playBtn.textContent = "▶ PLAY SELECTED";
}

export function bindControlsBar(root, handlers) {
  root
    .querySelector('[data-role="play-btn"]')
    .addEventListener("click", handlers.onPlay);
  root
    .querySelector('[data-role="step-btn"]')
    .addEventListener("click", handlers.onStep);
  root
    .querySelector('[data-role="auto-btn"]')
    .addEventListener("click", handlers.onToggleAuto);
}
